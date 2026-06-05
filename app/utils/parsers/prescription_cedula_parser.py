import re
from typing import Any, List, Optional


def procesar_receta_con_seguridad(
    texto: str, mantener_detalle_completo: bool = False
) -> Optional[List[dict[str, Any]]]:
    texto_min = texto.lower()

    tiene_palabra_cedula = re.search(r"c[eé]dula", texto_min)
    tiene_numero_cedula = re.search(r"\b\d{6,8}\b", texto_min)

    if not (tiene_palabra_cedula and tiene_numero_cedula):
        return None

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    medicamentos_encontrados: List[dict[str, Any]] = []

    for i, linea in enumerate(lineas):
        l_low = linea.lower()

        if "cada" in l_low and ("hora" in l_low or "hr" in l_low):
            horas_match = re.search(r"cada\s+(\d+)", l_low)
            horas = horas_match.group(1) if horas_match else "No detectado"

            dias_match = re.search(r"durante\s+(\d+)", l_low)
            dias = dias_match.group(1) if dias_match else "No detectado"

            via = None
            linea_para_via = (
                linea
                if "administraci" in l_low
                else (
                    lineas[i - 1]
                    if i > 0 and "administraci" in lineas[i - 1].lower()
                    else ""
                )
            )

            if linea_para_via:
                match_via = re.search(
                    r"administraci[oó]n\s+([a-zA-ZáéíóúÁÉÍÓÚ]+)",
                    linea_para_via,
                    re.IGNORECASE,
                )
                if match_via and match_via.group(1).strip():
                    via = match_via.group(1).strip().capitalize()

            nombre_med = "No identificado"
            bloque_texto_medicamento: List[str] = []

            for j in range(i - 1, max(-1, i - 8), -1):
                candidato = lineas[j].strip()
                candidato_low = candidato.lower()

                if len(candidato) < 4:
                    continue

                if "vía de administración" in candidato_low and j != i - 1 and j != i:
                    break

                if any(
                    x in candidato_low
                    for x in [
                        "fecha:",
                        "primer nivel",
                        "asegura tu",
                        "esta receta",
                        "folio",
                    ]
                ):
                    break

                bloque_texto_medicamento.insert(0, candidato)

                if re.match(
                    r"^\d{4,7}\s+(?!MG\b|ML\b|UI\b|G\b)", candidato, re.IGNORECASE
                ):
                    break

            if bloque_texto_medicamento:
                frase_completa = " ".join(bloque_texto_medicamento)

                frase_sin_clave = re.sub(
                    r"^\d{4,7}\s+(?!MG\b|ML\b|UI\b|G\b)",
                    "",
                    frase_completa,
                    flags=re.IGNORECASE,
                ).strip()

                if mantener_detalle_completo:
                    # NUEVO FLUJO: Para la bandeja de revisión (primera consulta), guarda el detalle completo
                    nombre_med = frase_sin_clave.strip(" -.").upper()
                else:
                    # FLUJO ORIGINAL: Para "enviar receta al paciente", recorta en base a las palabras clave
                    nombre_corto = frase_sin_clave.split(".")[0].strip()

                    palabras_corte = [
                        "GRAGEA",
                        "TABLETA",
                        "COMPRIMIDO",
                        "SOLUCION",
                        "CAPSULA",
                        "ENVASE",
                        "MG",
                        "ML",
                        "UI",
                        "SUSPENSION",
                        "JARABE",
                        "AMPOLLETA",
                    ]
                    patron_corte = r"\b(?:" + "|".join(palabras_corte) + r")\b"
                    match_corte = re.search(patron_corte, nombre_corto, flags=re.IGNORECASE)

                    if match_corte:
                        nombre_corto = nombre_corto[: match_corte.start()].strip()

                    nombre_med = (
                        nombre_corto.upper()
                        if nombre_corto
                        else frase_sin_clave.split()[0].upper()
                    )
                    nombre_med = nombre_med.strip(" -")

            medicamentos_encontrados.append(
                {
                    "medicamento": nombre_med,
                    "cada_cuantas_horas": horas,
                    "duracion_dias": dias,
                    "via_administracion": via,
                }
            )

    return medicamentos_encontrados