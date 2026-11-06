#!/usr/bin/env python3
"""Debug A3: check drug pattern matching."""
import re

drug_pattern = re.compile(
    r'\b([a-záéíóúñ]+(?:pril|sartan|lol|cilline|mycin|pram|oxina|'
    r'feno|zina|dipina|tidina|vir|navir|conazol|profeno|'
    r'formina|gliptina|gliflozina|agliflozina|statina|'
    r'ciclina|cef|prazol|triptilina|oxetina|azepam|barbital|'
    r'caina|mab|zumab|ximab|umab|cept|parina|coxib|'
    r'artán|tán))\b',
    re.IGNORECASE
)

tests = ["enalapril", "losartán", "amlodipino", "metformina", "captopril", "insulina", "glargina"]
for t in tests:
    m = drug_pattern.findall(t)
    print(f"  {t}: {m}")

# Also test the full text
src = "La combinación de enalapril y amlodipino redujo la presión arterial sistólica en 18 mmHg a las 12 semanas."
rsp = "La combinación de enalapril y losartán redujo la presión arterial sistólica en 18 mmHg a las 12 semanas."
print(f"\nSource drugs: {drug_pattern.findall(src)}")
print(f"Response drugs: {drug_pattern.findall(rsp)}")