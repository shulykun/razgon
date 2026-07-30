import re
content = open("app/templates/promo_v7.html").read()

replacements = [
    ("--brand-dark: #0d0520", "--brand-dark: #111111"),
    ("--brand-purple: #7c3aed", "--brand-purple: #1a1a1a"),
    ("--brand-violet: #a855f7", "--brand-violet: #333333"),
    ("--brand-orange: #f97316", "--brand-orange: #c8ff00"),
    ("--brand-pink: #ec4899", "--brand-pink: #e0ff4f"),
    ("rgba(124,58,237", "rgba(26,26,26"),
    ("rgba(249,115,22", "rgba(200,255,0"),
    ("rgba(168,85,247", "rgba(51,51,51"),
    ("rgba(236,72,153", "rgba(224,255,79"),
    ("#7c3aed", "#1a1a1a"),
    ("#a855f7", "#333333"),
    ("#f97316", "#c8ff00"),
    ("#ec4899", "#e0ff4f"),
]

for old, new in replacements:
    content = content.replace(old, new)

open("app/templates/promo_v7.html", "w").write(content)
print("OK")
