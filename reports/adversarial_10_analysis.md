# Adversarial Set — Failure Mode Analysis
## SAS Multimetric Tribunal v1.4.0
### Fecha: 2026-11-05

## Resultado global: 1/10 correctos (1/5 detect, 0/5 no_detect)

## Tipo A — Debe detectar (alucinación stealth): 1/5

### A1: Dosis 25→250 mg — FALLO (ISI=0.9130, COHERENTE, 0 módulos)
- **Causa**: source_target_guard no detecta mutación de cantidad porque "250" y "25" son ambos números. El módulo usa regex de entidades (proper nouns, años, cantidades) pero no compara valores numéricos específicos dentro de la misma clase.
- **Lección**: Module 2 detecta *presencia/ausencia* de entidades, no *mutación de valor*. Una dosis de 25→250 mg es semánticamente crítica pero estructuralmente invisible.
- **Recomendación**: Agregar comparación de valores numéricos dentro de la misma clase de entidad (ej: dosis 25→250 = mutación 10×).

### A3: Amlodipino→Losartán — FALLO (ISI=0.8889, COHERENTE, 0 módulos)
- **Causa**: source_target_guard no reconoce "amlodipino" ni "losartán" como entidades porque están en minúscula. El extractor usa `w[0].isupper()` como heurística. En texto médico, los fármacos van en minúscula.
- **Lección**: El extractor de entidades del Module 2 está calibrado para inglés (proper nouns con mayúscula). En español médico, los nombres de fármacos son minúscula y no se detectan.
- **Recomendación**: Agregar diccionario de fármacos comunes o usar gazetteer para entidades médicas.

### A4: Fecha 2024→2025 — FALLO PARCIAL (ISI=0.4225, RUPTURA_RECUPERABLE)
- **Causa**: source_target_guard detectó la mutación de fecha (disparó), pero la penalización no fue suficiente para llegar a COLAPSO (ISI=0.4225 ≥ κR=0.15 pero ≥ κD=0.56? No, está en RUPTURA).
- **Lección**: Una mutación de fecha simple no alcanza el umbral de colapso. El sistema la marca como "sospechosa" pero no como "alucinación".
- **Recomendación**: Evaluar si el peso de source_target_guard (0.25) es suficiente para mutaciones de fecha.

### A5: Relación causal invertida — FALLO (ISI=1.0000, COHERENTE, 0 módulos)
- **Causa**: flow_penalty no detecta inversión causal. El módulo mide entropía de segmentos, no relaciones causales. "A causó B" vs "B causó A" tienen exactamente las mismas palabras y entropía.
- **Lección**: El sistema no tiene ningún módulo que modele relaciones causales. La inversión causa-efecto es invisible.
- **Recomendación**: Este es un failure mode fundamental. Sin modelo semántico, la causalidad es indetectable. Documentar como límite del sistema.

### A2: Negación insertada — ÉXITO (ISI=0.1000, COLAPSO_ESTRUCTURAL)
- **Causa**: negation_penalty detectó "no reduce" vs "reduce". Penalización suficiente para colapso.
- **Lección**: El módulo de negación funciona correctamente en español.

## Tipo B — No debe detectar (paráfrasis legítima): 0/5

### B1: Reordenamiento de oraciones — FALLO (ISI=0.1245, COLAPSO)
- **Causa**: cre_isi disparó. El módulo LSA-based mide dispersión de embeddings. Al reordenar oraciones, la dispersión cambia aunque el contenido sea idéntico.
- **Lección**: cre_isi no es invariante a reordenamiento. Esto es consistente con el hallazgo del paper (\S\ref{sec:cre-contribution}): cre_isi responde a propiedades del texto, no a la relación source-response.
- **Módulos que dispararon**: ['cre_isi']

### B2: Activa→Pasiva — FALLO (ISI=0.0475, COLAPSO)
- **Causa**: 4 módulos dispararon (flow_penalty, negation_penalty, cre_isi, r3_6_surprisal). La transformación sintáctica cambia el orden de palabras, la entropía de segmentos, y la estructura de superficie.
- **Lección**: El sistema no es invariante a voz gramatical. Una paráfrasis legítima con activa→pasiva es clasificada como alucinación severa.
- **Módulos que dispararon**: ['flow_penalty', 'negation_penalty', 'cre_isi', 'r3_6_surprisal']

### B3: Sinónimos médicos — FALLO (ISI=0.3667, RUPTURA)
- **Causa**: r3_6_surprisal disparó. "Hiperglucemia" → "niveles elevados de glucosa" introduce tokens OOV (out-of-vocabulary) que el modelo de n-gramas del source no reconoce.
- **Lección**: El módulo de surprisal (R3.6) penaliza vocabulario nuevo incluso cuando es semánticamente equivalente. Esto es un false positive por diseño.
- **Módulos que dispararon**: ['r3_6_surprisal']

### B4: División de oraciones — FALLO (ISI=0.1362, COLAPSO)
- **Causa**: cre_isi disparó. Dividir una oración larga en 3 cortas cambia la dispersión LSA.
- **Lección**: Misma causa que B1. cre_isi no es invariante a estructura de oraciones.
- **Módulos que dispararon**: ['cre_isi']

### B5: Fusión de oraciones — FALLO (ISI=0.4342, RUPTURA)
- **Causa**: r3_6_surprisal disparó. La fusión introduce conectores ("con lo cual", "y") que no están en el source.
- **Lección**: Misma causa que B3. El surprisal penaliza conectores nuevos aunque sean gramaticales.
- **Módulos que dispararon**: ['r3_6_surprisal']

## Análisis transversal

### Patrón de fallos en Tipo A (debe detectar)
- **4/5 fallan** porque el sistema no tiene un módulo de **comparación semántica fina**.
- source_target_guard detecta presencia/ausencia de entidades, no mutación de valores.
- flow_penalty no modela relaciones causales.
- negation_penalty funciona (único éxito).

### Patrón de fallos en Tipo B (no debe detectar)
- **5/5 fallan** porque el sistema penaliza **cambio de forma** aunque el contenido sea idéntico.
- cre_isi dispara en reordenamiento y división (3/5 fallos).
- r3_6_surprisal dispara en sinónimos y fusión (2/5 fallos).
- flow_penalty + negation_penalty disparan en activa→pasiva (1/5).

### Implicación para el paper
El adversarial set confirma el scope statement: "SAS detecta alucinaciones estructurales con cobertura limitada a textos con overlap léxico ≥ 30% o estructura de entidades compartida." Los 10 casos están en el límite o fuera de ese scope.

**Valor del adversarial set:** No es 10/10. Es saber exactamente dónde se rompe. Y ahora lo sabemos.

## Recomendaciones (para próxima iteración, NO modificar ahora)
1. source_target_guard: agregar comparación de valores numéricos dentro de misma clase
2. Extractor de entidades: agregar gazetteer de fármacos para español médico
3. cre_isi: documentar que no es invariante a reordenamiento (ya está en \S\ref{sec:cre-contribution})
4. r3_6_surprisal: calibrar umbral OOV para no penalizar sinónimos
5. flow_penalty: agregar detección de inversión causal (requiere modelo semántico)