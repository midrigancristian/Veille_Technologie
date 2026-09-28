"""Keyword-based article categorizer (FR + EN)."""

import re
from html import unescape

CATEGORIES = {
    "dev": "Développement",
    "cyber": "Cybersécurité",
    "sysadmin": "SysAdmin",
    "ia": "IA",
    "autre": "Autre",
}

_CYBER = re.compile(
    r"("
    r"\bcve[- ]?\d{4}"
    r"|ransomware|malware|phishing|zero[\s-]?day|0[\s-]?day"
    r"|vulnerabilit(?:y|ies|é|e)"
    r"|cyber(?:securit|attaque|crime)?"
    r"|infosec|\bhack(?:er|ing|ed)?\b|breach|exploit"
    r"|s[eé]curit[eé]|firewall|botnet|pentest|owasp"
    r"|cryptograph|data[\s-]?leak|data[\s-]?breach"
    r"|apt\b|threat[\s-]?actor|ransom|spyware|trojan"
    r"|worm\b|backdoor|privilege[\s-]?escalation"
    r"|authentication|mfa\b|passkey|password"
    r"|certificat(?:e|s)|tls\b|https?\b.?vuln"
    r"|bleeping|krebs|red[\s-]?team|blue[\s-]?team"
    r"|soc\b|siem\b|xdr\b|edr\b|zero[\s-]?trust"
    r")",
    re.I,
)

_IA = re.compile(
    r"("
    r"\bllms?\b|\bgpts?\b|\bai\b|\bia\b"
    r"|openai|anthropic|\bclaude\b|chatgpt|gemini"
    r"|hugging\s?face|\bmistral\b|\bllama\b|\bqwen\b"
    r"|machine[\s-]?learning|deep[\s-]?learning|neural"
    r"|intelligence artificielle|g[eé]n[eé]rative"
    r"|stable[\s-]?diffusion|midjourney|diffusion model"
    r"|transformer|fine[\s-]?tun(?:e|ing)|rag\b"
    r"|agentic|copilot|\bdall-?e\b|multimodal"
    r"|inference|embedding|vector(?:iel)?|tokeni[sz]"
    r"|artificial intelligence|genai|foundation model"
    r")",
    re.I,
)

_SYS = re.compile(
    r"("
    r"kubernetes|\bk8s\b|\bdocker\b|containerd|podman"
    r"|terraform|ansible|puppet|chef\b|nixos|\bnix\b"
    r"|devops|sre\b|observabilit|prometheus|grafana"
    r"|linux|systemd|nginx|apache|caddy|traefik"
    r"|aws\b|azure|gcp\b|cloudflare|cloud native"
    r"|sysadmin|administrateur syst"
    r"|ci/?cd|github actions|gitlab ci"
    r"|helm\b|istio|service mesh|ebpf"
    r"|postgresql|mysql|redis|kafka"
    r"|virtuali[sz]|hypervisor|proxmox|vmware"
    r"|network(?:ing)?|dns\b|bgp\b|ipv6|firewalld"
    r"|backup|sauvegarde|monitoring"
    r")",
    re.I,
)

_DEV = re.compile(
    r"("
    r"javascript|typescript|\bpython\b|\brust\b|\bgo\b|golang"
    r"|java\b|kotlin|swift|c\+\+|c#|\.net|php\b|ruby"
    r"|react|vue\.?js|svelte|angular|next\.?js|django|flask|fastapi"
    r"|programming|programmation|developer|d[eé]veloppeur"
    r"|framework|library|open[\s-]?source|github"
    r"|api\b|sdk\b|compiler|runtime|debug"
    r"|git\b|pull request|\bpr\b|refactor"
    r"|frontend|back[\s-]?end|full[\s-]?stack"
    r"|webassembly|\bwasm\b|nodejs|npm\b"
    r")",
    re.I,
)

_NOISE = re.compile(
    r"("
    r"sponsored|publicit[eé]|offre d['’]emploi|recrutement"
    r"|black friday|promo(tion)?s?\b|code promo"
    r")",
    re.I,
)


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_noise(title: str, summary: str = "") -> bool:
    blob = f"{title} {summary}"
    return bool(_NOISE.search(blob))


def categorize(title: str, summary: str = "", default: str = "autre") -> str:
    blob = f"{title} {summary}"
    scores = {
        "cyber": len(_CYBER.findall(blob)),
        "ia": len(_IA.findall(blob)),
        "sysadmin": len(_SYS.findall(blob)),
        "dev": len(_DEV.findall(blob)),
    }
    best = max(scores, key=scores.get)
    if scores[best] >= 1:
        # Prefer more specific buckets when tied-ish
        if scores["cyber"] >= scores[best] and scores["cyber"] > 0:
            return "cyber"
        if scores["ia"] >= scores[best] and scores["ia"] > 0:
            return "ia"
        if scores["sysadmin"] > scores["dev"] and scores["sysadmin"] > 0:
            return "sysadmin"
        return best
    return default if default in CATEGORIES else "autre"
