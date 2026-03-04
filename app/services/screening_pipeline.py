import json
import asyncio
from typing import List, Optional, TypedDict
from datetime import datetime
from app.core.database import SessionLocal
from app.models.job import Job
from app.models.candidate import Candidate
from app.models.screening import Screening


# ── STATE DEFINITION ─────────────────────────────────────────────────────────
class ScreeningState(TypedDict):
    """
    Typed state object passed between every node in the LangGraph pipeline.
    Each node receives the full state, updates its own fields, and returns it.
    """
    job_id: str
    screening_id: str
    job_title: str
    job_description: str
    required_skills: str
    min_experience_years: int
    candidates_raw: List[dict]        # loaded from DB before graph starts
    candidates_scored: List[dict]     # filled by node_extract_and_score
    candidates_verified: List[dict]   # filled by node_verify_profiles
    candidates_ranked: List[dict]     # filled by node_rank_candidates
    error: Optional[str]


# ── BUILD GRAPH ───────────────────────────────────────────────────────────────
def build_screening_graph():
    """
    Constructs and compiles the LangGraph StateGraph.

    Node flow:
        START
          extract_and_score   -- LLM parses CV + scores each candidate
          verify_profiles     -- checks LinkedIn + GitHub
          rank_candidates     -- sorts by final score, assigns rank numbers
          save_results        -- persists everything to database
        END
    """
    from langgraph.graph import StateGraph, END, START

    graph = StateGraph(ScreeningState)

    graph.add_node("extract_and_score", node_extract_and_score)
    graph.add_node("verify_profiles",   node_verify_profiles)
    graph.add_node("rank_candidates",   node_rank_candidates)
    graph.add_node("save_results",      node_save_results)

    graph.add_edge(START,               "extract_and_score")
    graph.add_edge("extract_and_score", "verify_profiles")
    graph.add_edge("verify_profiles",   "rank_candidates")
    graph.add_edge("rank_candidates",   "save_results")
    graph.add_edge("save_results",      END)

    return graph.compile()


# ── NODE 1: EXTRACT AND SCORE ─────────────────────────────────────────────────
async def node_extract_and_score(state: ScreeningState) -> ScreeningState:
    """
    LangGraph Node 1 — CV Extraction and Scoring.

    Uses ChatGroq (langchain-groq) with Llama 3.3 70B to:
      - Extract structured fields from raw CV text
      - Score the candidate 0-100 against the job description

    One LLM call per candidate.
    3 second delay between calls to stay within Groq free tier limits.
    """
    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.core.config import settings

    total = len(state["candidates_raw"])
    print(f"[Node 1] extract_and_score — {total} candidates")

    llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model="llama-3.3-70b-versatile",
        temperature=0.1,
        max_tokens=1024,
    )

    system = SystemMessage(content=(
        "You are TalentMesh, a senior recruitment specialist with 20 years of experience "
        "screening candidates across technology, data, and business roles. "
        "You score candidates based on genuine potential, not just keyword matching. "
        "Your scoring follows these principles:\n"
        "1. TRANSFERABLE SKILLS: You have a comprehensive list of equivalent tools in the scoring prompt. "
        "Always check equivalents before marking a skill as missing. "
        "A candidate with deep expertise in an equivalent tool scores the same as one with the exact tool.\n"
        "2. LEARNING POTENTIAL: A candidate with 80% of required skills plus strong "
        "adjacent experience should score 65-75%, not 20-30%. "
        "Penalise missing skills proportionally — not harshly for tools that can be learned.\n"
        "3. EXPERIENCE DEPTH: 5 years in a directly adjacent role is worth more than "
        "1 year in the exact role. Weight quality of experience over job title matching.\n"
        "4. HONEST JUSTIFICATION: Explain the score logically. "
        "State what they have, what transfers, what is genuinely missing, "
        "and whether the gap is learnable or fundamental.\n"
        "Return valid JSON only. No markdown, no backticks, no explanation."
    ))

    scored = []

    for i, c in enumerate(state["candidates_raw"]):
        label = c.get("full_name") or c.get("email") or f"Candidate {i+1}"
        print(f"  [{i+1}/{total}] {label}")

        if i > 0:
            await asyncio.sleep(3.0)

        # Handle image-based PDFs (Canva etc.) — run vision OCR now
        raw_text = (c.get("cv_raw_text") or "").strip()
        if not raw_text and c.get("cv_file_path"):
            print(f"  No text for {label} — running vision OCR")
            from app.services.cv_parser import extract_with_vision_ocr
            raw_text = await asyncio.to_thread(
                extract_with_vision_ocr, c["cv_file_path"]
            )
            # Save OCR result back to DB for future use
            db_ocr = SessionLocal()
            try:
                db_ocr.query(Candidate).filter(
                    Candidate.id == c["id"]
                ).update({"cv_raw_text": raw_text})
                db_ocr.commit()
            finally:
                db_ocr.close()
        if not raw_text:
            print(f"  Still no text for {label} — skipping")
            scored.append(_fallback(c, "Could not extract text from CV"))
            continue

        human = HumanMessage(content=(
            "Evaluate this candidate thoroughly for the role below.\n\n"
            f"JOB TITLE: {state['job_title']}\n"
            f"JOB DESCRIPTION: {state['job_description'][:1000]}\n"
            f"REQUIRED SKILLS: {state['required_skills']}\n"
            f"MINIMUM EXPERIENCE: {state['min_experience_years']} years\n\n"
            f"CV TEXT:\n{raw_text[:3000]}\n\n"
            "SCORING GUIDE:\n"
            "- 85-100%: Has all required skills (including equivalents) + strong relevant experience\n"
            "- 70-84%:  Has most required skills, strong adjacent experience, small learnable gaps\n"
            "- 55-69%:  Has 60-70% of required skills, meaningful transferable experience\n"
            "- 40-54%:  Has some relevant skills but significant gaps or different specialisation\n"
            "- 20-39%:  Adjacent field, limited direct relevance, steep learning curve\n"
            "- 0-19%:   Wrong role entirely, no meaningful transferable skills\n\n"
            "TRANSFERABLE SKILLS — treat these as equivalent when scoring:\n"
            "\n"
            "DATA & BI:\n"
            "- BI Tools:        Power BI ↔ Tableau ↔ Cognos ↔ Qlik ↔ Looker ↔ MicroStrategy ↔ Metabase ↔ Superset\n"
            "- SQL Databases:   PostgreSQL ↔ MySQL ↔ Oracle ↔ MSSQL ↔ SQLite ↔ MariaDB\n"
            "- Cloud Warehouses:Snowflake ↔ BigQuery ↔ Redshift ↔ Azure Synapse ↔ Databricks\n"
            "- ETL/Pipeline:    dbt ↔ Informatica ↔ Talend ↔ SSIS ↔ Fivetran ↔ Airbyte ↔ Matillion\n"
            "- Orchestration:   Airflow ↔ Prefect ↔ Dagster ↔ Luigi ↔ Azure Data Factory\n"
            "- Notebooks:       Jupyter ↔ Google Colab ↔ Databricks Notebooks ↔ Zeppelin\n"
            "\n"
            "SOFTWARE ENGINEERING:\n"
            "- Backend:         Python ↔ Java ↔ Go ↔ C# ↔ Node.js ↔ Ruby (all are backend languages)\n"
            "- Frontend:        React ↔ Vue ↔ Angular ↔ Svelte (all are component frameworks)\n"
            "- APIs:            REST ↔ GraphQL ↔ gRPC (all are API paradigms)\n"
            "- Frameworks:      FastAPI ↔ Django ↔ Flask ↔ Express ↔ Spring Boot ↔ Rails\n"
            "- ORMs:            SQLAlchemy ↔ Django ORM ↔ Hibernate ↔ Sequelize\n"
            "- Testing:         pytest ↔ unittest ↔ Jest ↔ JUnit ↔ Mocha (same concept different language)\n"
            "\n"
            "CLOUD & DEVOPS:\n"
            "- Cloud Platforms: AWS ↔ Azure ↔ GCP (transferable, not identical)\n"
            "- Containers:      Docker ↔ Podman\n"
            "- Orchestration:   Kubernetes ↔ EKS ↔ GKE ↔ AKS ↔ OpenShift\n"
            "- IaC:             Terraform ↔ Pulumi ↔ CloudFormation ↔ Bicep\n"
            "- CI/CD:           GitHub Actions ↔ GitLab CI ↔ Jenkins ↔ CircleCI ↔ Azure DevOps\n"
            "- Monitoring:      Datadog ↔ Grafana ↔ Prometheus ↔ New Relic ↔ CloudWatch\n"
            "- Logging:         ELK Stack ↔ Splunk ↔ Loki ↔ Sumo Logic\n"
            "\n"
            "MACHINE LEARNING & AI:\n"
            "- ML Frameworks:   PyTorch ↔ TensorFlow ↔ JAX (deep learning frameworks)\n"
            "- ML Libraries:    scikit-learn ↔ XGBoost ↔ LightGBM ↔ CatBoost\n"
            "- MLOps:           MLflow ↔ Weights & Biases ↔ Neptune ↔ Kubeflow\n"
            "- Vector DBs:      Pinecone ↔ Weaviate ↔ Chroma ↔ Qdrant ↔ Milvus\n"
            "- LLM Frameworks:  LangChain ↔ LlamaIndex ↔ Haystack\n"
            "- Feature Stores:  Feast ↔ Tecton ↔ Hopsworks\n"
            "\n"
            "PRODUCT & PROJECT MANAGEMENT:\n"
            "- Agile Tools:     Jira ↔ Linear ↔ Trello ↔ Asana ↔ Monday ↔ Azure Boards\n"
            "- Docs/Wiki:       Confluence ↔ Notion ↔ Coda ↔ SharePoint\n"
            "- Design:          Figma ↔ Sketch ↔ Adobe XD ↔ InVision\n"
            "- Analytics:       Google Analytics ↔ Mixpanel ↔ Amplitude ↔ Heap\n"
            "\n"
            "MESSAGING & STREAMING:\n"
            "- Message Queues:  Kafka ↔ RabbitMQ ↔ AWS SQS ↔ Azure Service Bus ↔ Pub/Sub\n"
            "- Streaming:       Kafka Streams ↔ Apache Flink ↔ Spark Streaming\n"
            "\n"
            "CRM & BUSINESS TOOLS:\n"
            "- CRM:             Salesforce ↔ HubSpot ↔ Dynamics 365 ↔ Zoho\n"
            "- ERP:             SAP ↔ Oracle ERP ↔ Microsoft Dynamics ↔ NetSuite\n"
            "- HR Systems:      Workday ↔ SAP SuccessFactors ↔ BambooHR ↔ ADP\n"
            "\n"
            "IMPORTANT NUANCE:\n"
            "- Cloud platforms (AWS/Azure/GCP) are transferable at concept level but not identical — "
            "note the specific platform mismatch in skills_missing if relevant but do not penalise heavily.\n"
            "- A candidate with deep expertise in one language/framework can learn an equivalent — "
            "treat as a partial match, not a miss.\n"
            "- Years of experience in an equivalent role/tool should count toward the experience requirement.\n\n"
            "Return ONLY this JSON object:\n"
            "{\n"
            '  "full_name": "candidate full name from CV",\n'
            '  "email": "email address or null",\n'
            '  "location": "city and country or null",\n'
            '  "skills": "comma separated list of ALL technical skills found",\n'
            '  "experience_years": 4,\n'
            '  "education": "degree, field, university, year",\n'
            '  "work_history": "2-3 sentence summary of work experience and companies",\n'
            '  "match_score": 75,\n'
            '  "justification": "3-4 sentences: what they have, what transfers, what is missing and whether that gap is learnable or fundamental",\n'
            '  "red_flags": "genuine concerns only — not having an exact tool when they have an equivalent is NOT a red flag. Null if none.",\n'
            '  "skills_matched": "required skills this candidate has, including equivalent tools",\n'
            '  "skills_missing": "required skills with no equivalent found in the CV"\n'
            "}"
        ))

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, [system, human]),
                timeout=25.0
            )
            text = response.content.strip()

            # Strip markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            result = json.loads(text)
            score  = max(0, min(100, int(result.get("match_score", 0))))

            scored.append({
                "candidate_id":     c["id"],
                "full_name":        result.get("full_name") or c.get("full_name"),
                "email":            result.get("email") or c.get("email"),
                "skills":           result.get("skills", ""),
                "experience_years": int(result.get("experience_years") or 0),
                "education":        result.get("education"),
                "work_history":     result.get("work_history"),
                "match_score":      score,
                "justification":    result.get("justification", ""),
                "red_flags":        result.get("red_flags"),
                "linkedin_url":     c.get("linkedin_url"),
                "github_url":       c.get("github_url"),
            })
            print(f"  Score: {score}% — {result.get('full_name') or label}")

        except asyncio.TimeoutError:
            print(f"  Timeout: {label}")
            scored.append(_fallback(c, "LLM request timed out after 25s"))
        except json.JSONDecodeError as e:
            print(f"  JSON parse error for {label}: {e}")
            scored.append(_fallback(c, f"Could not parse LLM response: {e}"))
        except Exception as e:
            print(f"  Error for {label}: {e}")
            scored.append(_fallback(c, str(e)))

    return {**state, "candidates_scored": scored}


# ── NODE 2: VERIFY PROFILES ─────────────────────────────────────────────────
async def node_verify_profiles(state: ScreeningState) -> ScreeningState:
    """
    LangGraph Node 2 — External Profile Verification across 4 platforms.

      Platform       Condition                        Bonus
      ──────────────────────────────────────────────────────
      LinkedIn       Profile URL returns 200           +3
      GitHub         5+ repos                          +4  (+1 per 20 repos, max +6)
      Kaggle         Verified + tier                   +2 to +5
      StackOverflow  Verified + reputation             +1 to +5

      Maximum total bonus:  +10 (hard capped)

    All four checks run concurrently per candidate.
    Each check skips gracefully if credentials are not configured on Render.
    """
    from app.services.linkedin_service      import verify_linkedin
    from app.services.github_service        import verify_github
    from app.services.kaggle_service        import verify_kaggle, kaggle_tier_score
    from app.services.stackoverflow_service import verify_stackoverflow, stackoverflow_reputation_score

    total = len(state["candidates_scored"])
    print(f"[Node 2] verify_profiles — {total} candidates")

    async def _safe(coro):
        """Run a coroutine and return None on any error."""
        try:
            return await coro
        except Exception:
            return None

    verified = []
    for c in state["candidates_scored"]:
        bonus = 0
        notes = []

        # Run all four checks concurrently for this candidate
        linkedin_data, github_data, kaggle_data, so_data = await asyncio.gather(
            _safe(asyncio.wait_for(verify_linkedin(c.get("linkedin_url") or ""), timeout=8.0))
            if c.get("linkedin_url") else asyncio.sleep(0, result=None),
            _safe(asyncio.wait_for(verify_github(c.get("github_url") or ""), timeout=10.0))
            if c.get("github_url") else asyncio.sleep(0, result=None),
            _safe(asyncio.wait_for(verify_kaggle(c.get("kaggle_url") or ""), timeout=10.0))
            if c.get("kaggle_url") else asyncio.sleep(0, result=None),
            _safe(asyncio.wait_for(verify_stackoverflow(c.get("stackoverflow_url") or ""), timeout=10.0))
            if c.get("stackoverflow_url") else asyncio.sleep(0, result=None),
        )

        # LinkedIn: +3 for confirmed public profile
        if linkedin_data and linkedin_data.get("exists"):
            bonus += 3
            notes.append("LinkedIn verified")

        # GitHub: +4 base + up to +2 for repo volume
        if github_data:
            repos = github_data.get("public_repos", 0)
            if repos >= 5:
                gh_bonus = min(6, 4 + repos // 20)
                bonus += gh_bonus
                langs = ", ".join(github_data.get("top_languages", [])[:3])
                notes.append(f"GitHub {repos} repos ({langs})")

        # Kaggle: +2 to +5 by tier (Novice → Grandmaster)
        if kaggle_data:
            tier    = kaggle_data.get("tier", "Novice")
            k_bonus = kaggle_tier_score(tier)
            if k_bonus > 0:
                bonus += k_bonus
                notes.append(f"Kaggle {tier}")

        # StackOverflow: +1 to +5 by reputation
        if so_data:
            rep      = so_data.get("reputation", 0)
            so_bonus = stackoverflow_reputation_score(rep)
            if so_bonus > 0:
                bonus += so_bonus
                tags = ", ".join(so_data.get("top_tags", [])[:3])
                notes.append(f"SO rep {rep:,} ({tags})")

        # Hard cap
        bonus = min(10, bonus)

        if notes:
            c["justification"] += " Verified profiles: " + " | ".join(notes) + "."
        c["match_score"] = min(100, c["match_score"] + bonus)

        name = c.get("full_name") or "Unknown"
        if bonus > 0:
            print(f"  {name}: +{bonus} pts — {', '.join(notes)}")
        else:
            print(f"  {name}: no external profiles verified")

        verified.append(c)

    return {**state, "candidates_verified": verified}


# ── NODE 3: RANK CANDIDATES ───────────────────────────────────────────────────
async def node_rank_candidates(state: ScreeningState) -> ScreeningState:
    """
    LangGraph Node 3 — Ranking.

    Sorts all verified candidates by match_score descending.
    Assigns rank numbers starting from 1.
    Prints the final leaderboard to Render logs.
    """
    print(f"[Node 3] rank_candidates")

    ranked = sorted(
        state["candidates_verified"],
        key=lambda x: x["match_score"],
        reverse=True
    )
    for i, c in enumerate(ranked):
        c["rank"] = i + 1

    print("  --- Final Ranking ---")
    for c in ranked:
        name = (c.get("full_name") or "Unknown")[:28]
        print(f"  #{c['rank']:<3} {name:<28} {c['match_score']}%")

    return {**state, "candidates_ranked": ranked}


# ── NODE 4: SAVE RESULTS ──────────────────────────────────────────────────────
async def node_save_results(state: ScreeningState) -> ScreeningState:
    """
    LangGraph Node 4 — Database Persistence.

    Saves all extracted CV fields, scores, ranks, and justifications.
    This is the final node before END.
    """
    total = len(state["candidates_ranked"])
    print(f"[Node 4] save_results — persisting {total} records")

    db = SessionLocal()
    try:
        for c in state["candidates_ranked"]:
            db.query(Candidate).filter(Candidate.id == c["candidate_id"]).update({
                "full_name":           c.get("full_name"),
                "email":               c.get("email"),
                "skills":              c.get("skills"),
                "experience_years":    c.get("experience_years", 0),
                "education":           c.get("education"),
                "work_history":        c.get("work_history"),
                "match_score":         c["match_score"],
                "rank":                c["rank"],
                "score_justification": c.get("justification"),
                "red_flags":           c.get("red_flags"),
            })
        db.commit()
        print(f"  Saved {total} candidates to database")
    finally:
        db.close()

    return state


# ── FALLBACK HELPER ───────────────────────────────────────────────────────────
def _fallback(candidate: dict, reason: str) -> dict:
    """Returns a zero-score record when a candidate cannot be scored."""
    return {
        "candidate_id":     candidate["id"],
        "full_name":        candidate.get("full_name"),
        "email":            candidate.get("email"),
        "skills":           candidate.get("skills", ""),
        "experience_years": candidate.get("experience_years", 0),
        "education":        candidate.get("education"),
        "work_history":     candidate.get("work_history"),
        "match_score":      0,
        "justification":    f"Automatic scoring failed. Reason: {reason}",
        "red_flags":        "Could not score automatically — review manually.",
        "linkedin_url":     candidate.get("linkedin_url"),
        "github_url":       candidate.get("github_url"),
    }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
async def run_screening_pipeline(job_id: str, screening_id: str):
    """
    Called by POST /api/v1/screen/{job_id}.

    Loads job + candidates from DB, builds the LangGraph StateGraph,
    prepares the initial state, and runs graph.ainvoke().
    """
    db = SessionLocal()
    try:
        screening = db.query(Screening).filter(Screening.id == screening_id).first()
        screening.status = "processing"
        db.commit()

        job        = db.query(Job).filter(Job.id == job_id).first()
        candidates = db.query(Candidate).filter(Candidate.job_id == job_id).all()

        print(f"\n{'='*55}")
        print(f"  TalentMesh — LangGraph Screening Pipeline")
        print(f"  Job:        {job.title}")
        print(f"  Candidates: {len(candidates)}")
        print(f"{'='*55}")

        initial_state: ScreeningState = {
            "job_id":               job_id,
            "screening_id":         screening_id,
            "job_title":            job.title,
            "job_description":      job.description or "",
            "required_skills":      job.required_skills or "",
            "min_experience_years": job.min_experience_years or 0,
            "candidates_raw": [
                {
                    "id":               c.id,
                    "full_name":        c.full_name,
                    "email":            c.email,
                    "cv_raw_text":      c.cv_raw_text,
                    "skills":           c.skills,
                    "experience_years": c.experience_years,
                    "education":        c.education,
                    "work_history":     c.work_history,
                    "linkedin_url":       c.linkedin_url,
                    "github_url":         c.github_url,
                    "kaggle_url":         c.kaggle_url,
                    "stackoverflow_url":  getattr(c, "stackoverflow_url", None),
                }
                for c in candidates
            ],
            "candidates_scored":   [],
            "candidates_verified": [],
            "candidates_ranked":   [],
            "error":               None,
        }

        graph = build_screening_graph()
        await graph.ainvoke(initial_state)

        screening.status       = "completed"
        screening.completed_at = datetime.utcnow()
        db.query(Job).filter(Job.id == job_id).update({"status": "completed"})
        db.commit()

        print(f"\n  Pipeline complete: {job.title}")
        print(f"{'='*55}\n")

    except Exception as e:
        print(f"Pipeline failed: {e}")
        import traceback; traceback.print_exc()
        try:
            s = db.query(Screening).filter(Screening.id == screening_id).first()
            if s:
                s.status        = "failed"
                s.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
