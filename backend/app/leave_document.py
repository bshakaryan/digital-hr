"""Minimal DOCX from an approved request, not a company-approved HR template."""
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def leave_document(item, employee, *, demo: bool) -> bytes:
    lines = ["Демонстрационный документ — подпись имитируется" if demo else "Проект заявления на отпуск — проверьте перед подписанием",
        f"Заявка JanaМен №{item.id}", f"Организация: {employee.company}",
        f"Сотрудник: {employee.full_name}", f"Должность: {employee.position}",
        f"Прошу предоставить ежегодный отпуск с {item.start_date.isoformat()} по {item.end_date.isoformat()}.",
        f"К списанию: {item.days_count} календарных дней. Версия календаря: {item.calendar_version}.",
        f"Комментарий: {item.comment}", "Документ сформирован из согласованной заявки. Форма требует утверждения HR."]
    def xml_text(value):
        # XML 1.0 does not allow NUL/control characters or unpaired surrogates.
        return escape("".join(ch for ch in value if ch in "\t\n\r" or "\u0020" <= ch <= "\ud7ff" or "\ue000" <= ch <= "\ufffd" or "\U00010000" <= ch <= "\U0010ffff"))
    paragraphs = "".join(f'<w:p><w:r><w:t xml:space="preserve">{xml_text(line)}</w:t></w:r></w:p>' for line in lines)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paragraphs}</w:body></w:document>')
    return buffer.getvalue()
