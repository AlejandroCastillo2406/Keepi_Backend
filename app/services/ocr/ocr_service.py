import logging
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self):
        self.textract_client = boto3.client("textract", region_name="us-east-1")
        self.s3_client = boto3.client("s3")

    async def extract_text_from_document(
        self, file_path: str, file_type: str
    ) -> Dict[str, Any]:
        try:
            if file_type.lower() in ["pdf"]:
                return await self._process_pdf(file_path)
            elif file_type.lower() in ["jpg", "jpeg", "png", "tiff", "bmp"]:
                return await self._process_image(file_path)
            else:
                raise ValueError(f"Tipo de archivo no soportado: {file_type}")

        except Exception as e:
            logger.error(f"Error en OCR: {str(e)}")
            raise

    async def _process_pdf(self, file_path: str) -> Dict[str, Any]:
        try:

            with open(file_path, "rb") as file:
                pdf_bytes = file.read()

            response = self.textract_client.analyze_document(
                Document={"Bytes": pdf_bytes},
                FeatureTypes=["TABLES", "FORMS", "SIGNATURES"],
            )

            return self._parse_textract_response(response)

        except Exception as e:
            logger.error(f"Error procesando PDF: {str(e)}")
            raise

    async def _process_image(self, file_path: str) -> Dict[str, Any]:
        try:

            with open(file_path, "rb") as file:
                image_bytes = file.read()

            response = self.textract_client.analyze_document(
                Document={"Bytes": image_bytes},
                FeatureTypes=["TABLES", "FORMS", "SIGNATURES"],
            )

            return self._parse_textract_response(response)

        except Exception as e:
            logger.error(f"Error procesando imagen: {str(e)}")
            raise

    def _parse_textract_response(self, response: Dict) -> Dict[str, Any]:
        extracted_data = {
            "full_text": "",
            "tables": [],
            "forms": [],
            "signatures": [],
            "dates": [],
            "numbers": [],
            "emails": [],
            "phones": [],
        }

        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                extracted_data["full_text"] += block["Text"] + "\n"

        for block in response.get("Blocks", []):
            if block["BlockType"] == "TABLE":
                table_data = self._extract_table_data(block, response["Blocks"])
                extracted_data["tables"].append(table_data)

        for block in response.get("Blocks", []):
            if block["BlockType"] == "KEY_VALUE_SET":
                if block.get("EntityTypes", []) == ["KEY"]:
                    form_data = self._extract_form_data(block, response["Blocks"])
                    extracted_data["forms"].append(form_data)

        for block in response.get("Blocks", []):
            if block["BlockType"] == "SIGNATURE":
                extracted_data["signatures"].append(
                    {
                        "confidence": block.get("Confidence", 0),
                        "geometry": block.get("Geometry", {}),
                    }
                )

        import re

        date_patterns = [
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            r"\b\d{1,2}\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{2,4}\b",
            r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{1,2},?\s+\d{2,4}\b",
        ]

        for pattern in date_patterns:
            dates = re.findall(pattern, extracted_data["full_text"], re.IGNORECASE)
            extracted_data["dates"].extend(dates)

        number_patterns = [r"\b\d+\.?\d*\b", r"\$\d+\.?\d*\b", r"\b\d+\.?\d*%\b"]

        for pattern in number_patterns:
            numbers = re.findall(pattern, extracted_data["full_text"])
            extracted_data["numbers"].extend(numbers)

        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        extracted_data["emails"] = re.findall(
            email_pattern, extracted_data["full_text"]
        )

        phone_patterns = [
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            r"\(\d{3}\)\s*\d{3}[-.]?\d{4}\b",
            r"\+\d{1,3}\s*\d{3,4}[-.]?\d{3,4}[-.]?\d{3,4}\b",
        ]

        for pattern in phone_patterns:
            phones = re.findall(pattern, extracted_data["full_text"])
            extracted_data["phones"].extend(phones)

        return extracted_data

    def _extract_table_data(self, table_block: Dict, all_blocks: List[Dict]) -> Dict:
        table_data = {"rows": [], "columns": []}

        cells = []
        for relationship in table_block.get("Relationships", []):
            if relationship["Type"] == "CHILD":
                for cell_id in relationship["Ids"]:
                    cell_block = next(
                        (b for b in all_blocks if b["Id"] == cell_id), None
                    )
                    if cell_block and cell_block["BlockType"] == "CELL":
                        cells.append(cell_block)

        if cells:
            max_row = max(cell.get("RowIndex", 0) for cell in cells)
            max_col = max(cell.get("ColumnIndex", 0) for cell in cells)

            for row in range(1, max_row + 1):
                row_data = []
                for col in range(1, max_col + 1):
                    cell = next(
                        (
                            c
                            for c in cells
                            if c.get("RowIndex") == row and c.get("ColumnIndex") == col
                        ),
                        None,
                    )
                    if cell:
                        cell_text = self._get_cell_text(cell, all_blocks)
                        row_data.append(cell_text)
                    else:
                        row_data.append("")
                table_data["rows"].append(row_data)

        return table_data

    def _extract_form_data(self, key_block: Dict, all_blocks: List[Dict]) -> Dict:
        form_data = {"key": "", "value": ""}

        for relationship in key_block.get("Relationships", []):
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    child_block = next(
                        (b for b in all_blocks if b["Id"] == child_id), None
                    )
                    if child_block and child_block["BlockType"] == "WORD":
                        form_data["key"] += child_block["Text"] + " "

        for relationship in key_block.get("Relationships", []):
            if relationship["Type"] == "VALUE":
                for value_id in relationship["Ids"]:
                    value_block = next(
                        (b for b in all_blocks if b["Id"] == value_id), None
                    )
                    if value_block:
                        for value_rel in value_block.get("Relationships", []):
                            if value_rel["Type"] == "CHILD":
                                for child_id in value_rel["Ids"]:
                                    child_block = next(
                                        (b for b in all_blocks if b["Id"] == child_id),
                                        None,
                                    )
                                    if (
                                        child_block
                                        and child_block["BlockType"] == "WORD"
                                    ):
                                        form_data["value"] += child_block["Text"] + " "

        return form_data

    def _get_cell_text(self, cell_block: Dict, all_blocks: List[Dict]) -> str:
        cell_text = ""
        for relationship in cell_block.get("Relationships", []):
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    child_block = next(
                        (b for b in all_blocks if b["Id"] == child_id), None
                    )
                    if child_block and child_block["BlockType"] == "WORD":
                        cell_text += child_block["Text"] + " "
        return cell_text.strip()

    async def extract_document_metadata(
        self, file_path: str, file_type: str
    ) -> Dict[str, Any]:
        ocr_data = await self.extract_text_from_document(file_path, file_type)

        metadata = {
            "extracted_text": ocr_data["full_text"],
            "document_type": self._detect_document_type(ocr_data),
            "key_dates": ocr_data["dates"],
            "key_numbers": ocr_data["numbers"],
            "contact_info": {
                "emails": ocr_data["emails"],
                "phones": ocr_data["phones"],
            },
            "has_signature": len(ocr_data["signatures"]) > 0,
            "has_tables": len(ocr_data["tables"]) > 0,
            "has_forms": len(ocr_data["forms"]) > 0,
        }

        return metadata

    def _detect_document_type(self, ocr_data: Dict) -> str:
        text = ocr_data["full_text"].lower()

        if any(word in text for word in ["factura", "invoice", "bill", "cobro"]):
            return "factura"
        elif any(
            word in text for word in ["contrato", "contract", "acuerdo", "agreement"]
        ):
            return "contrato"
        elif any(
            word in text
            for word in ["identificación", "id", "cedula", "passport", "licencia"]
        ):
            return "identificación"
        elif any(
            word in text for word in ["recibo", "receipt", "comprobante", "voucher"]
        ):
            return "recibo"
        elif any(
            word in text for word in ["certificado", "certificate", "diploma", "título"]
        ):
            return "certificado"
        elif any(word in text for word in ["reporte", "report", "informe", "análisis"]):
            return "reporte"
        else:
            return "documento_general"
