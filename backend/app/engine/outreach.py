"""Multilingual (Telugu / Hindi / English) two-way outreach agent - deterministic core.

Design rules (guardrails):
  * NO clinical advice, ever. The agent handles logistics only.
  * Symptom / emergency language -> RED_FLAG: hand over to a human, nothing but a safety message.
  * Anything that promises support, changes an appointment, or is low-confidence waits in the
    human approval queue. Only acknowledgements and menus are sent automatically.
  * Every inbound message is stored with its parsed intent/barrier -> fully auditable.

Why rules and not an LLM? Reliability + zero API cost for the demo. If ANTHROPIC_API_KEY is set,
`classify_with_llm` can be used for low-confidence messages (see services.py) - same output schema.

NOTE: Telugu/Hindi templates are drafted for the demo and should be reviewed by a native speaker
before any real deployment.
"""
from __future__ import annotations

import re

LANGS = {"te": "Telugu", "hi": "Hindi", "en": "English"}

BARRIERS = {
    "TRANSPORT": "Transport / distance",
    "COST": "Cost / money",
    "FEAR": "Fear / anxiety",
    "UNDERSTANDING": "Did not understand",
    "WORK_LEAVE": "Work / cannot take leave",
    "UNREACHABLE": "Phone unreachable / wrong number",
    "RELOCATED": "Moved away",
}

# ---- templates -------------------------------------------------------------------------------
T = {
    "reminder": {
        "en": "Hello {name}, your health check needs a follow-up visit at {facility}. Reply 1 to confirm, 2 to change the date, 3 if you need help.",
        "hi": "नमस्ते {name} जी, आपकी स्वास्थ्य जांच के अगले चरण के लिए {facility} में आपका इंतज़ार है। पक्का करने के लिए 1, तारीख बदलने के लिए 2, मदद के लिए 3 भेजें।",
        "te": "నమస్కారం {name} గారు, మీ ఆరోగ్య పరీక్ష తదుపరి సందర్శన కోసం {facility}లో మీ కోసం ఎదురు చూస్తున్నాం. నిర్ధారించడానికి 1, తేదీ మార్చడానికి 2, సహాయం కావాలంటే 3 అని రిప్లై చేయండి.",
    },
    "appt_reminder": {
        "en": "Hello {name}, reminder: your appointment at {facility} is on {when}. Reply 1 to confirm, 2 to change the date, 3 for help.",
        "hi": "नमस्ते {name} जी, याद दिलाना: {facility} में आपका अपॉइंटमेंट {when} को है। पक्का करने के लिए 1, तारीख बदलने के लिए 2, मदद के लिए 3 भेजें।",
        "te": "నమస్కారం {name} గారు, గుర్తు చేస్తున్నాం: {facility}లో మీ అపాయింట్‌మెంట్ {when} న ఉంది. నిర్ధారించడానికి 1, తేదీ మార్చడానికి 2, సహాయం కోసం 3 పంపండి.",
    },
    "ack_confirm": {
        "en": "Thank you {name}. Your visit is confirmed. We will remind you before the date.",
        "hi": "धन्यवाद {name} जी। आपकी विज़िट पक्की हो गई है। तारीख से पहले हम याद दिलाएंगे।",
        "te": "ధన్యవాదాలు {name} గారు. మీ సందర్శన నిర్ధారించబడింది. తేదీకి ముందు మేము గుర్తు చేస్తాము.",
    },
    "ack_reached": {
        "en": "Thank you {name}. Our care coordinator will call you shortly to fix a convenient day.",
        "hi": "धन्यवाद {name} जी। हमारे केयर कोऑर्डिनेटर जल्द ही आपको सुविधाजनक दिन तय करने के लिए कॉल करेंगे।",
        "te": "ధన్యవాదాలు {name} గారు. అనుకూలమైన రోజును నిర్ణయించడానికి మా కేర్ కోఆర్డినేటర్ త్వరలో మీకు కాల్ చేస్తారు.",
    },
    "reschedule": {
        "en": "No problem {name}. We can move your visit to {when}. Reply 1 to accept or tell us a day that suits you.",
        "hi": "कोई बात नहीं {name} जी। हम आपकी विज़िट {when} को कर सकते हैं। मंज़ूर हो तो 1 भेजें या अपनी सुविधा का दिन बताएं।",
        "te": "పరవాలేదు {name} గారు. మీ సందర్శనను {when}కి మార్చగలం. అంగీకారమైతే 1 పంపండి లేదా మీకు వీలైన రోజు చెప్పండి.",
    },
    "optout": {
        "en": "{name}, you will not receive any more messages from us. If you change your mind, tell your ASHA or the health centre.",
        "hi": "{name} जी, अब आपको हमारी ओर से कोई संदेश नहीं भेजा जाएगा। मन बदले तो अपनी आशा या स्वास्थ्य केंद्र को बताएं।",
        "te": "{name} గారు, ఇకపై మీకు మా నుంచి సందేశాలు రావు. మనసు మారితే మీ ఆశా కార్యకర్తకు లేదా ఆరోగ్య కేంద్రానికి చెప్పండి.",
    },
    "menu": {
        "en": "Sorry to hear that, {name}. What is the main problem? 1 = Transport, 2 = Cost, 3 = Fear/worry, 4 = Work/leave, 5 = Something else.",
        "hi": "यह जानकर दुख हुआ {name} जी। मुख्य समस्या क्या है? 1 = आने-जाने का साधन, 2 = खर्च, 3 = डर/चिंता, 4 = काम/छुट्टी, 5 = कुछ और।",
        "te": "క్షమించండి {name} గారు. ప్రధాన సమస్య ఏమిటి? 1 = రవాణా, 2 = ఖర్చు, 3 = భయం/ఆందోళన, 4 = పని/సెలవు, 5 = ఇంకేదైనా.",
    },
    "support_TRANSPORT": {
        "en": "Thank you for telling us, {name}. We will arrange travel support and an ASHA worker will contact you about a visit day.",
        "hi": "बताने के लिए धन्यवाद {name} जी। हम आने-जाने में मदद की व्यवस्था करेंगे और आशा कार्यकर्ता आपसे विज़िट के दिन के बारे में संपर्क करेंगी।",
        "te": "చెప్పినందుకు ధన్యవాదాలు {name} గారు. ప్రయాణ సహాయం ఏర్పాటు చేస్తాం, సందర్శన రోజు గురించి ఆశా కార్యకర్త మిమ్మల్ని సంప్రదిస్తారు.",
    },
    "support_COST": {
        "en": "Thank you for telling us, {name}. Our team will check which government health schemes can cover your visit and call you.",
        "hi": "बताने के लिए धन्यवाद {name} जी। हमारी टीम देखेगी कि कौन-सी सरकारी स्वास्थ्य योजना आपकी विज़िट का खर्च उठा सकती है और आपको कॉल करेगी।",
        "te": "చెప్పినందుకు ధన్యవాదాలు {name} గారు. మీ సందర్శన ఖర్చును ఏ ప్రభుత్వ ఆరోగ్య పథకాలు భరిస్తాయో మా బృందం చూసి మీకు కాల్ చేస్తుంది.",
    },
    "support_FEAR": {
        "en": "Thank you for sharing that, {name}. It is normal to feel worried. An ASHA worker will visit to answer your questions and go with you if you wish.",
        "hi": "बताने के लिए धन्यवाद {name} जी। चिंता होना स्वाभाविक है। आशा कार्यकर्ता आपके सवालों के जवाब देने आएंगी और चाहें तो आपके साथ चलेंगी।",
        "te": "పంచుకున్నందుకు ధన్యవాదాలు {name} గారు. ఆందోళన కలగడం సహజం. మీ సందేహాలకు సమాధానం చెప్పడానికి ఆశా కార్యకర్త వస్తారు, మీకు కావాలంటే మీతో కూడా వస్తారు.",
    },
    "support_UNDERSTANDING": {
        "en": "Thank you, {name}. We will call you and explain the next step slowly in your language.",
        "hi": "धन्यवाद {name} जी। हम आपको कॉल करके अगला कदम आपकी भाषा में आराम से समझाएंगे।",
        "te": "ధన్యవాదాలు {name} గారు. మేము మీకు కాల్ చేసి తదుపరి అడుగును మీ భాషలో నెమ్మదిగా వివరిస్తాము.",
    },
    "support_WORK_LEAVE": {
        "en": "Thank you, {name}. We will look for an evening or weekend slot that suits your work and call you.",
        "hi": "धन्यवाद {name} जी। हम आपके काम के अनुसार शाम या सप्ताहांत का समय खोजकर आपको कॉल करेंगे।",
        "te": "ధన్యవాదాలు {name} గారు. మీ పనికి అనువైన సాయంత్రం లేదా వారాంతపు సమయం చూసి మీకు కాల్ చేస్తాము.",
    },
    "support_RELOCATED": {
        "en": "Thank you, {name}. Tell us your new village/town and we will move your referral to a nearby facility.",
        "hi": "धन्यवाद {name} जी। अपना नया गाँव/शहर बताएं, हम आपका रेफरल पास की सुविधा में भेज देंगे।",
        "te": "ధన్యవాదాలు {name} గారు. మీ కొత్త గ్రామం/పట్టణం చెప్పండి, మీ రెఫరల్‌ను సమీప సదుపాయానికి మారుస్తాము.",
    },
    "support_OTHER": {
        "en": "Thank you, {name}. A coordinator will call you to understand and help.",
        "hi": "धन्यवाद {name} जी। एक कोऑर्डिनेटर आपको समझने और मदद करने के लिए कॉल करेंगे।",
        "te": "ధన్యవాదాలు {name} గారు. అర్థం చేసుకుని సహాయం చేయడానికి కోఆర్డినేటర్ మీకు కాల్ చేస్తారు.",
    },
    "red_flag": {
        "en": "{name}, we cannot give medical advice on chat. If this feels like an emergency, call 108 now or go to the nearest hospital. A clinician from our team will contact you.",
        "hi": "{name} जी, हम चैट पर चिकित्सा सलाह नहीं दे सकते। अगर यह आपातकाल लगे तो अभी 108 पर कॉल करें या नज़दीकी अस्पताल जाएं। हमारी टीम का चिकित्सक आपसे संपर्क करेगा।",
        "te": "{name} గారు, చాట్‌లో వైద్య సలహా ఇవ్వలేము. ఇది అత్యవసరం అనిపిస్తే వెంటనే 108కి కాల్ చేయండి లేదా సమీప ఆసుపత్రికి వెళ్లండి. మా బృందంలోని వైద్యులు మిమ్మల్ని సంప్రదిస్తారు.",
    },
    "facility_nudge": {
        "en": "Reminder: {name} attended on {when}. Please confirm the visit outcome in CuraLoop to close the loop.",
        "hi": "याद दिलाना: {name} {when} को आए थे। लूप बंद करने के लिए कृपया CuraLoop में विज़िट का परिणाम पुष्ट करें।",
        "te": "గుర్తు: {name} {when} న వచ్చారు. లూప్ మూసివేయడానికి దయచేసి CuraLoopలో విజిట్ ఫలితాన్ని నిర్ధారించండి.",
    },
}


def render(template: str, lang: str, **kw) -> str:
    block = T[template]
    text = block.get(lang) or block["en"]
    return text.format(**kw)


# ---- parsing ---------------------------------------------------------------------------------
_TELUGU = re.compile(r"[ఀ-౿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

DIGIT_MAP = str.maketrans({"१": "1", "२": "2", "३": "3", "४": "4", "५": "5",
                           "౧": "1", "౨": "2", "౩": "3", "౪": "4", "౫": "5"})

# keyword -> barrier. Native script + common romanised spellings (people type Telugu/Hindi in Latin).
BARRIER_KEYWORDS = {
    "TRANSPORT": ["bus", "transport", "vehicle", "auto", "gaadi", "gadi", "door", "dooram", "doorame", "far away",
                  "travel", "ride", "vaahanam", "vahanam", "చాలా దూరం", "దూరం", "రవాణా", "బస్సు", "వాహనం",
                  "दूर", "गाड़ी", "बस नहीं", "साधन", "आने-जाने"],
    "COST": ["money", "cost", "paisa", "paise", "kharcha", "kharch", "expensive", "dabbulu", "dabbu", "fees",
             "afford", "ఖర్చు", "డబ్బు", "డబ్బులు", "पैसा", "पैसे", "खर्च", "महंगा"],
    "FEAR": ["afraid", "scared", "fear", "worried", "nervous", "dar lag", "darr", "dar hai", "bhay", "bhayam",
             "bhayamga", "భయం", "భయంగా", "ఆందోళన", "डर", "घबराहट", "चिंता"],
    "UNDERSTANDING": ["don't understand", "dont understand", "do not understand", "samajh nahi", "samjha nahi",
                      "ardham kaaledu", "ardam kaaledu", "ardham kaledu", "what is this", "అర్థం కాలేదు",
                      "అర్ధం కాలేదు", "समझ नहीं", "समझ नही"],
    "WORK_LEAVE": ["work", "job", "duty", "leave", "chhutti", "kaam", "pani", "panilo", "coolie", "farm",
                   "పని", "సెలవు", "కూలి", "काम", "छुट्टी", "ड्यूटी", "खेत"],
    "RELOCATED": ["moved", "shifted", "relocated", "left the village", "gaon chhod", "shift ho", "migrated",
                  "వెళ్లిపోయాం", "మారాము", "షిఫ్ట్", "शिफ्ट", "गाँव छोड़"],
}
CONFIRM_WORDS = ["yes", "ok", "okay", "confirm", "confirmed", "sure", "haan", "han ", "theek", "thik", "avunu",
                 "sare", "sari", "vastanu", "vastaanu", "అవును", "సరే", "వస్తాను", "हाँ", "हां", "ठीक", "जी"]
RESCHEDULE_WORDS = ["reschedule", "another day", "other day", "change date", "change the date", "later", "next week",
                    "kal", "agle hafte", "tareekh badal", "tarikh badal", "vere roju", "marchandi", "repu",
                    "తేదీ మార్చ", "వేరే రోజు", "తర్వాత", "तारीख बदल", "दूसरे दिन", "बाद में"]
OPT_OUT_WORDS = ["stop", "unsubscribe", "opt out", "do not contact", "mat bhejo", "मत भेजो", "పంపవద్దు"]
HELP_WORDS = ["help", "problem", "issue", "madad", "sahayam", "sahaayam", "samasya", "సహాయం", "సమస్య", "मदद", "समस्या"]
RED_FLAG_WORDS = ["chest pain", "can't breathe", "cant breathe", "breathless", "bleeding", "blood", "faint", "unconscious",
                  "severe pain", "emergency", "dard", "seene mein", "saans", "khoon", "behosh", "noppi", "ūpiri", "upiri",
                  "rakta", "raktam", "poyaadu", "ఛాతీ నొప్పి", "నొప్పి", "రక్తం", "ఊపిరి", "స్పృహ",
                  "सीने में दर्द", "दर्द", "सांस", "खून", "बेहोश"]


def detect_language(text: str, hint: str = "en") -> str:
    if _TELUGU.search(text):
        return "te"
    if _DEVANAGARI.search(text):
        return "hi"
    return hint if hint in LANGS else "en"


def parse_message(text: str, *, awaiting_menu: bool = False, lang_hint: str = "en") -> dict:
    """Return {intent, barrier, red_flag, language, confidence}.

    intent in CONFIRM / RESCHEDULE / HELP / BARRIER / OPT_OUT / RED_FLAG / UNKNOWN
    """
    raw = (text or "").strip()
    norm = raw.translate(DIGIT_MAP).lower()
    lang = detect_language(raw, lang_hint)
    res = {"intent": "UNKNOWN", "barrier": None, "red_flag": False, "language": lang, "confidence": "low"}
    if not norm:
        return res

    # safety first
    if any(w in norm for w in RED_FLAG_WORDS):
        res.update(intent="RED_FLAG", red_flag=True, confidence="high")
        return res

    # consent withdrawal beats everything except safety
    if norm in {"stop", "unsubscribe"} or any(w in norm for w in OPT_OUT_WORDS if " " in w or len(w) > 6):
        res.update(intent="OPT_OUT", confidence="high")
        return res

    # follow-up to the barrier menu: single digit 1-5
    if awaiting_menu and norm in {"1", "2", "3", "4", "5"}:
        mapping = {"1": "TRANSPORT", "2": "COST", "3": "FEAR", "4": "WORK_LEAVE", "5": None}
        res.update(intent="BARRIER", barrier=mapping[norm], confidence="high")
        return res

    if norm in {"1", "1."}:
        res.update(intent="CONFIRM", confidence="high")
        return res
    if norm in {"2", "2."}:
        res.update(intent="RESCHEDULE", confidence="high")
        return res
    if norm in {"3", "3."}:
        res.update(intent="HELP", confidence="high")
        return res

    # barrier keywords (most informative -> check before generic confirm/help)
    scores = {}
    for barrier, words in BARRIER_KEYWORDS.items():
        hits = sum(1 for w in words if w.lower() in norm)
        if hits:
            scores[barrier] = hits
    if scores:
        best = max(scores, key=scores.get)
        res.update(intent="BARRIER", barrier=best, confidence="high" if scores[best] >= 1 else "medium")
        return res

    if any(w in norm for w in RESCHEDULE_WORDS):
        res.update(intent="RESCHEDULE", confidence="medium")
        return res
    if any(w in norm for w in HELP_WORDS):
        res.update(intent="HELP", confidence="medium")
        return res
    padded = f" {norm} "
    if any((f" {w.strip()} " in padded) or norm.startswith(w.strip() + " ") or norm == w.strip() for w in CONFIRM_WORDS):
        res.update(intent="CONFIRM", confidence="medium")
        return res
    return res
