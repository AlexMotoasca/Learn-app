from flask import Blueprint, request, jsonify, current_app
from utils.ollama_client import call_ollama_generate
import os
import json
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.user import User
import re

chatbot = Blueprint("chatbot", __name__)

SYSTEM_INSTR = (
    "Ești un asistent virtual specializat în biologie pentru liceu.\n"
    "- Răspunde concis și în limba română.\n"
    "- Dacă ți se dă un context (textul unei lecții sau numărul unui modul), folosește informațiile din acel context ca primă sursă.\n"
    "- Dacă nu găsești informația în context, poți folosi cunoștințe generale de biologie, dar evită speculațiile nefondate; dacă nu știi, spune 'Nu știu'.\n"
    "- Dacă informația NU se găsește în contextul modulelor utilizatorului, răspunde cu O SINGURĂ PROPOZIȚIE standard și concisă în limba română, folosind formatul:\n"
    "  '<Subiect> este un proces biologic complex care nu este menționat în modululele de biologie pe care le-ai facut.'\n"
    "  Înlocuiește <Subiect> cu tema întrebării (de ex. 'Fotosinteza este un proces biologic complex...').\n"
    "  Nu adăuga alte explicații, nu folosi «Nu știu» și nu face referiri la «textul» sau «lecția».\n"
    "- Furnizează răspunsuri clare, structurate și, când e util, include un scurt exemplu sau o referință la sursa din context (de ex. 'conform lecției, paragraful X').\n"
)


def build_prompt(user_prompt: str, context_text: str | None = None, history: list | None = None) -> str:
    parts = [SYSTEM_INSTR.strip()]

    if context_text:
        parts.append("CONTEXT LECTIE:\n" + context_text.strip())

    # include a short history if provided (user/bot alternating)
    if history:
        hist_lines = ["Istoric conversație:"]
        for msg in history[-6:]:  # keep last few
            who = msg.get("from") or msg.get("role") or "user"
            text = msg.get("text") or ""
            hist_lines.append(f"{who}: {text}")
        parts.append("\n".join(hist_lines))

    parts.append("ÎNTREBAREA UTILIZATORULUI:\n" + user_prompt.strip())

    # ask the model to answer in Romanian and be concise
    parts.append("RESPUNDE ÎN LIMBA ROMÂNĂ, RĂSPUNS CONCIS:")

    return "\n\n".join(parts)


@chatbot.route("/respond", methods=["POST"])  # mounted at /api/chatbot/respond
@jwt_required()
def respond():
    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt")
    module = body.get("module")
    # ignore any arbitrary context_text from request to enforce module-only responses
    history = body.get("history")
    # optional: max chars to include from combined context (protect model input size)
    max_context_chars = body.get("max_context_chars") or 12000
    try:
        max_context_chars = int(max_context_chars)
    except Exception:
        max_context_chars = 12000

    if not prompt or not str(prompt).strip():
        return jsonify({"msg": "prompt required"}), 400

    # Helper: load text of one module file
    def load_module_text(n):
        p = os.path.join("Lessons", "biologie", f"modul{n}.txt")
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as fh:
                return fh.read()
        return None

    # Load user and their modules
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    def _safe_load(s):
        try:
            v = json.loads(s) if s else []
            return [int(x) for x in v] if isinstance(v, list) else []
        except Exception:
            return []

    user_in_prog = _safe_load(getattr(user, "modules_in_progress", "[]"))
    user_completed = _safe_load(getattr(user, "completed_modules", "[]"))

    allowed_modules = sorted(set(user_in_prog + user_completed))

    if not allowed_modules:
        return jsonify({"msg": "User has no modules in progress or completed; chatbot cannot respond."}), 400

    # Determine which modules to use for this request
    modules_to_use = []
    if module is not None:
        # If module provided, accept single int or list but ensure all are in allowed_modules
        if isinstance(module, list):
            for m in module:
                try:
                    mi = int(m)
                except Exception:
                    continue
                if mi not in allowed_modules:
                    return jsonify({"msg": f"module {mi} not allowed for this user"}), 403
                modules_to_use.append(mi)
        elif isinstance(module, str) and module.lower() in ("all", "*"):
            modules_to_use = allowed_modules
        else:
            try:
                mi = int(module)
            except Exception:
                return jsonify({"msg": "module must be numeric, a list of numbers, or 'all'"}), 400
            if mi not in allowed_modules:
                return jsonify({"msg": f"module {mi} not allowed for this user"}), 403
            modules_to_use = [mi]
    else:
        # default: use user's allowed modules
        modules_to_use = allowed_modules

    # Collect lesson texts for the selected modules ONLY
    texts = []
    for n in modules_to_use:
        t = load_module_text(n)
        if t is None:
            return jsonify({"msg": f"module {n} not found on disk"}), 404
        texts.append(f"--- Modul {n} ---\n" + t)

    combined_context = "\n\n".join(texts)

    # Trim combined_context to max_context_chars
    if len(combined_context) > max_context_chars:
        combined_context = combined_context[-max_context_chars:]

    # Build prompt using only the modules' context
    prompt_payload = build_prompt(prompt, context_text=combined_context, history=history)

    try:
        result = call_ollama_generate(prompt_payload)
    except Exception as e:
        current_app.logger.exception("Ollama generate failed")
        return jsonify({"msg": "model error", "error": str(e)}), 500

    # Post-process: if model says info is missing, return a single standardized sentence
    try:
        low = (result or "").lower()
        not_found_patterns = [
            "nu știu",
            "nu stiu",
            "nu conțin",
            "nu contine",
            "nu găsește",
            "nu gaseste",
            "nu este menționat",
            "nu este mentionat",
            "nu există în",
            "nu exista in",
            "nu se găsește",
            "nu se gaseste",
        ]
        if any(p in low for p in not_found_patterns):
            # derive a subject from the prompt
            subj = (prompt or "subiect").strip()
            subj = re.sub(r"[\?\.!]$", "", subj).strip()
            subj = re.sub(r"(?i)^(care\s+sunt|care\s+este|ce\s+sunt|ce\s+este|explic[ăa]|explica|descrie|definește|defineste|cum|de\s+ce)\b", "", subj).strip()
            # remove leading words like 'etapele'
            subj = re.sub(r"(?i)^etapele\s+", "", subj).strip()
            # try to normalize common terms (example: fotosintezei -> Fotosinteza)
            m = re.search(r"(?i)(fotosintez\w*)", subj)
            if m:
                subj = "Fotosinteza"
            else:
                subj = subj.capitalize()
            std = f"{subj} este un proces biologic complex care nu este menționat în modulul de biologie pe care îl ai."
            return jsonify({"reply": std}), 200
    except Exception:
        pass

    return jsonify({"reply": result}), 200
