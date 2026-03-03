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
        "You are TalentMesh, an expert AI recruitment screening agent. "
        "Extract structured data from CVs and score candidates against job requirements. "
        "Return valid JSON only. No markdown, no backticks, no explanation."
    ))

    scored = []

    for i, c in enumerate(state["candidates_raw"]):
        label = c.get("full_name") or c.get("email") or f"Candidate {i+1}"
        print(f"  [{i+1}/{total}] {label}")

        if i > 0:
            await asyncio.sleep(3.0)

        raw_text = (c.get("cv_raw_text") or "").strip()
        if not raw_text:
            print(f"  No CV text for {label} — skipping")
            scored.append(_fallback(c, "No CV text found in database"))
            continue

        human = HumanMessage(content=(
            "Extract structured data and score this candidate for the role below.\n\n"
            f"JOB TITLE: {state['job_title']}\n"
            f"JOB DESCRIPTION: {state['job_description'][:1000]}\n"
            f"REQUIRED SKILLS: {state['required_skills']}\n"
            f"MINIMUM EXPERIENCE: {state['min_experience_years']} years\n\n"
            f"CV TEXT:\n{raw_text[:3000]}\n\n"
            "Return ONLY this JSON object:\n"
            "{\n"
            '  "full_name": "candidate full name from CV",\n'
            '  "email": "email address or null",\n'
            '  "location": "city and country or null",\n'
            '  "skills": "comma separated list of all technical skills",\n'
            '  "experience_years": 4,\n'
            '  "education": "degree, field, university, year",\n'
            '  "work_history": "2-3 sentence summary of work experience",\n'
            '  "match_score": 75,\n'
            '  "justification": "2-3 sentences explaining why this score was given",\n'
            '  "red_flags": "any concerns about this candidate or null",\n'
            '  "skills_matched": "required skills this candidate has",\n'
            '  "skills_missing": "required skills this candidate lacks"\n'
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


# ── NODE 2: VERIFY PROFILES ───────────────────────────────────────────────────
async def node_verify_profiles(state: ScreeningState) -> ScreeningState:
    """
    LangGraph Node 2 — External Profile Verification.

    Checks LinkedIn and GitHub for each candidate.
    Awards bonus points for verified active profiles:
      +5 for verified LinkedIn
      +5 for active GitHub (more than 5 public repos)
      Max +10 total bonus

    Skips gracefully if credentials are not set on Render.
    """
    from app.services.linkedin_service import verify_linkedin
    from app.services.github_service import verify_github

    total = len(state["candidates_scored"])
    print(f"[Node 2] verify_profiles — {total} candidates")

    verified = []
    for c in state["candidates_scored"]:
        bonus = 0

        if c.get("linkedin_url"):
            try:
                data = await asyncio.wait_for(
                    verify_linkedin(c["linkedin_url"]), timeout=8.0
                )
                if data:
                    bonus += 5
                    c["justification"] += " LinkedIn profile verified."
                    print(f"  LinkedIn verified: {c.get('full_name')}")
            except Exception:
                pass

        if c.get("github_url"):
            try:
                data = await asyncio.wait_for(
                    verify_github(c["github_url"]), timeout=8.0
                )
                if data and data.get("public_repos", 0) > 5:
                    bonus += 5
                    c["justification"] += f" Active GitHub: {data.get('public_repos')} public repos."
                    print(f"  GitHub verified: {c.get('full_name')} ({data.get('public_repos')} repos)")
            except Exception:
                pass

        c["match_score"] = min(100, c["match_score"] + bonus)
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
                    "linkedin_url":     c.linkedin_url,
                    "github_url":       c.github_url,
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
