from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.user import User
from utils.ollama_client import call_ollama_generate
import datetime
import json
import re

user_quiz = Blueprint("user_quiz", __name__)

# Simple daily quiz provider: returns generated questions from module(s) or context
@user_quiz.route("/daily", methods=["GET"])  # /api/quiz/daily
@jwt_required()
def daily_quiz():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # Lazy import helpers from quiz_routes to reuse prompt/JSON extraction
    from routes.quiz_routes import retrieve_context, build_prompt, extract_json_block

    # Accept optional query params: module (int or 'all'), count
    module_param = request.args.get("module")
    count = int(request.args.get("count", 5))

    # Helper to load modules list from user model (JSON text)
    def _safe_load(s):
        try:
            v = json.loads(s) if s else []
            return [int(x) for x in v] if isinstance(v, list) else []
        except Exception:
            return []

    user_in_prog = _safe_load(getattr(user, "modules_in_progress", "[]"))
    user_completed = _safe_load(getattr(user, "completed_modules", "[]"))

    modules_to_use = []

    if module_param:
        # explicit module requested
        if isinstance(module_param, str) and module_param.lower() in ("all", "*"):
            modules_to_use = sorted(set(user_in_prog + user_completed))
            if not modules_to_use:
                return jsonify({"msg": "User has no modules in progress or completed"}), 400
        else:
            # allow comma-separated list or single number
            vals = [p.strip() for p in str(module_param).replace('-', ',').split(',') if p.strip()]
            nums = []
            for v in vals:
                try:
                    nums.append(int(v))
                except Exception:
                    pass
            if not nums:
                return jsonify({"msg": "Invalid module parameter"}), 400
            modules_to_use = nums
    else:
        # default: use user's modules in progress or completed
        modules_to_use = sorted(set(user_in_prog + user_completed))
        if not modules_to_use:
            return jsonify({"msg": "No modules found for user. Add modules to profile or pass ?module=1"}), 400

    # Collect lesson texts for the selected modules
    contexts = []
    for m in modules_to_use:
        try:
            ctx = retrieve_context(int(m), k=6)
            if ctx:
                contexts.extend(ctx)
        except Exception:
            continue

    if not contexts:
        return jsonify({"msg": "No lesson text available for selected modules"}), 404

    # Trim/limit combined context to avoid huge prompts
    combined = "\n\n".join(contexts[:6])
    # Build prompt similar to quiz_routes.build_prompt but ask for count questions
    # Start from the regular build_prompt (which enforces the JSON block format)
    base_prompt = build_prompt(combined).replace("Generează EXACT 5 întrebări grilă pe baza textului.", f"Generează EXACT {count} întrebări grilă pe baza textului.")

    # Add strict supplemental instructions so the model produces independent, concise explanations
    supplemental = (
        "\n\nINSTRUCȚIUNI SUPLIMENTARE PENTRU EXPLICAȚII:\n"
        "- Folosește atât informațiile din text, cât și cunoștințe externe corecte pentru a formula explicații.\n"
        "- NU menționa «textul», «conform lecției», «potrivit textului» sau alte referințe la sursă; explicațiile trebuie să fie independente de sursă.\n"
        "- Fiecare câmp 'explanation' trebuie să conțină 1–2 propoziții concise și convingătoare (maxim ~35 cuvinte).\n"
        "- Răspunde DOAR cu blocul JSON solicitat (<<<JSON ... JSON;). Nu adăuga niciun text în exteriorul blocului JSON."
    )

    lesson_prompt = base_prompt + supplemental

    try:
        result = call_ollama_generate(lesson_prompt)
    except Exception as e:
        current_app.logger.exception("model error")
        return jsonify({"msg": "model error", "error": str(e)}), 500

    questions, err = extract_json_block(result)
    if err:
        # if model didn't return the strict JSON block, return raw reply plus error info
        return jsonify({"msg": "no structured JSON detected", "raw": result, "error": err}), 200

    # sanitize explanations to avoid referring to "textul" or "conform lecției"
    def _sanitize_explanation(text: str) -> str:
        if not text or not isinstance(text, str):
            return text or ""
        t = text
        # remove common source-referring phrases in Romanian
        t = re.sub(r'(?i)\btextul\s+(menționează|menționeaza|menționat|precizează|precizeaza|spune|arată|arata|specifică|specifica|indică|indica)\b', '', t)
        t = re.sub(r'(?i)\b(textul\s+(specifică|specifica|indică|indica)\s*că)\b', '', t)
        t = re.sub(r'(?i)\b(conform\s+lec[iî]ei|conform\s+textului|potrivit\s+textului|potrivit\s+lec[iî]ei|conform\s+lecției)\b', '', t)
        t = re.sub(r'(?i)\b(potrivit|conform)\b', '', t)
        # remove leftover phrases like 'după text' or 'în text'
        t = re.sub(r'(?i)\b(în\s+text|după\s+text)\b', '', t)
        # remove leading Romanian conjunction 'că' if it starts the explanation (common bad starts)
        t = re.sub(r'(?i)^\s*(că|ca)\s+', '', t)
        # remove repeated spaces and stray punctuation
        t = re.sub(r'\s+', ' ', t).strip()
        t = t.lstrip(':-–— ').strip()
        if not t:
            return "Explicație scurtă."
        # ensure it ends with a period
        if not t.endswith('.') and not t.endswith('!') and not t.endswith('?'):
            t = t + '.'
        # capitalize first character
        t = t[0].upper() + t[1:]
        return t

    # apply sanitation to each question
    try:
        for q in questions:
            if isinstance(q, dict):
                q['explanation'] = _sanitize_explanation(q.get('explanation', ''))
    except Exception:
        # if sanitation fails, ignore and return original questions
        pass

    # Regenerate explanations using the model to ensure they are developed and independent
    try:
        for q in questions:
            if not isinstance(q, dict):
                continue
            # build a strict per-question prompt
            try:
                correct_idx = int(q.get('correct_index', 0))
                correct_choice = q.get('options', [])[correct_idx] if isinstance(q.get('options'), list) and len(q.get('options')) > correct_idx else None
            except Exception:
                correct_choice = None

            perq_prompt = (
                "Generează o explicație concisă în limba română (1–2 propoziții, max 35 cuvinte) pentru următoarea întrebare,\n"
                "explicând de ce răspunsul corect este corect și, dacă e relevant, de ce celelalte variante sunt greșite.\n"
                "Nu menționa «textul», «conform lecției» sau alte referințe la sursă; explicatia trebuie să fie independentă de sursă.\n"
                "Răspunde DOAR cu textul explicației (fără JSON sau alte comentarii).\n\n"
                f"Întrebare: {q.get('question')}\n"
                f"Opțiuni: {json.dumps(q.get('options', []), ensure_ascii=False)}\n"
            )
            if correct_choice:
                perq_prompt += f"Răspuns corect: {correct_choice}\n"

            try:
                out = call_ollama_generate(perq_prompt, max_tokens=150)
                if out and isinstance(out, str) and out.strip():
                    gen = _sanitize_explanation(out.strip())
                    # shorten to 1-2 sentences and limit words to ~35
                    def _shorten_explanation(text: str) -> str:
                        if not text or not isinstance(text, str):
                            return ""
                        # split into sentences (simple split by .!?), keep first 2
                        parts = re.split(r'(?<=[\.!?])\s+', text.strip())
                        if not parts:
                            return text.strip()
                        sel = parts[0:2]
                        outt = ' '.join(sel).strip()
                        # ensure max ~35 words
                        words = outt.split()
                        if len(words) > 35:
                            outt = ' '.join(words[:35]).rstrip(' ,;:') + '.'
                        # ensure ends with punctuation
                        if outt and outt[-1] not in '.!?':
                            outt = outt + '.'
                        # capitalize
                        outt = outt[0].upper() + outt[1:]
                        return outt

                    q['explanation'] = _shorten_explanation(gen)
            except Exception:
                # if model call fails, keep existing sanitized explanation
                pass
    except Exception:
        # if anything goes wrong, ignore regeneration and return sanitized questions
        pass

    return jsonify({"modules": modules_to_use, "questions": questions}), 200


# Submit quiz results
@user_quiz.route("/submit", methods=["POST"])  # /api/quiz/submit
@jwt_required()
def submit_quiz():
    body = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # Expected body: { "score": int, "max_score": int, "questions_correct": int, "questions_total": int, "module": int (optional) }
    score = body.get("score")
    max_score = body.get("max_score") or body.get("questions_total")
    correct = body.get("questions_correct")
    total = body.get("questions_total")
    module = body.get("module")

    if score is None and correct is None:
        return jsonify({"msg": "score or questions_correct required"}), 400

    # Determine points to add to total_score (prefer raw correct count if provided)
    try:
        if correct is not None:
            points = int(correct)
        elif score is not None:
            # if a raw score (points) provided, use that
            points = int(score)
        else:
            points = 0
    except Exception:
        points = 0

    # compute percentage for completion threshold
    percent = None
    try:
        if correct is not None and total:
            percent = (int(correct) / int(total)) * 100
        elif score is not None and max_score:
            percent = (int(score) / int(max_score)) * 100
        elif score is not None:
            percent = float(score)
    except Exception:
        percent = None

    # update total_score (add points)
    try:
        user.total_score = (user.total_score or 0) + int(points)
    except Exception:
        user.total_score = (user.total_score or 0)

    today = datetime.date.today()
    updated_streak = user.current_streak or 0

    if user.last_quiz_date is None:
        updated_streak = 1
    else:
        if user.last_quiz_date == today - datetime.timedelta(days=1):
            updated_streak = (user.current_streak or 0) + 1
        elif user.last_quiz_date == today:
            updated_streak = user.current_streak or 0
        else:
            updated_streak = 1

    user.current_streak = updated_streak
    if (user.longest_streak or 0) < updated_streak:
        user.longest_streak = updated_streak

    user.last_quiz_date = today

    # Defensive check: ensure User model has the module columns
    if not (hasattr(user, 'modules_in_progress') and hasattr(user, 'completed_modules')):
        # give clear instructions to run the helper script that adds the columns
        return jsonify({
            "msg": "Database schema missing columns for module progress.",
            "action": "Run: python scripts\\apply_db_alter_env.py then restart the server",
            "note": "If you previously dropped the users table, recreate it or run migrations."
        }), 500

    # Module progression logic
    def _safe_load(s):
        try:
            v = json.loads(s) if s else []
            return [int(x) for x in v] if isinstance(v, list) else []
        except Exception:
            return []

    in_prog = _safe_load(user.modules_in_progress)
    completed = _safe_load(user.completed_modules)

    if module is not None:
        try:
            module = int(module)
        except Exception:
            module = None

    if module:
        # if not recorded anywhere, add to in_progress
        if module not in in_prog and module not in completed:
            in_prog.append(module)

        # determine completion: threshold 70% or correct/total >= 0.7
        completed_flag = False
        try:
            if percent is not None:
                completed_flag = (percent >= 70)
            else:
                # fallback: use numeric score if present
                completed_flag = int(score) >= 70 if score is not None else False
        except Exception:
            completed_flag = False

        if completed_flag:
            # move module from in_progress to completed
            if module in in_prog:
                in_prog = [m for m in in_prog if m != module]
            if module not in completed:
                completed.append(module)

    # write back lists as JSON text
    user.modules_in_progress = json.dumps(sorted(set(in_prog)))
    user.completed_modules = json.dumps(sorted(set(completed)))

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "msg": "quiz recorded",
        "total_score": user.total_score,
        "current_streak": user.current_streak,
        "longest_streak": user.longest_streak,
        "last_quiz_date": user.last_quiz_date.isoformat(),
        "modules_in_progress": json.loads(user.modules_in_progress),
        "completed_modules": json.loads(user.completed_modules)
    }), 200
