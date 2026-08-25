import re
p = 'services/document_service.py'
s = open(p).read()

# 1) Fix the doubled-indent on the extraction session.commit() line that was
#    introduced by the previous whitespace-mangled edit (it is immediately
#    followed by the notification comment we inserted).
s = s.replace(
    "                session.commit()\n\n        # ---- Event-driven notifications",
    "        session.commit()\n\n        # ---- Event-driven notifications",
    1,
)

# 2) Capture document details for the "document deleted" notification BEFORE
#    the row is deleted from the session.
s = s.replace(
    "        # 1. Delete files\n        user_storage = os.path.join(DOCUMENT_STORAGE_PATH, str(user_id))",
    "        # Capture details for the \"document deleted\" notification before removal.\n"
    "        doc_filename = document.original_filename\n"
    "        doc_id = document.id\n"
    "        doc_user_id = document.user_id\n\n"
    "        # 1. Delete files\n        user_storage = os.path.join(DOCUMENT_STORAGE_PATH, str(user_id))",
    1,
)

# 3) Fire the "document deleted" notification after the DB row is removed.
s = s.replace(
    "        logger.info(\"Document deleted: id=%d, user=%d\", document_id, user_id)\n\n"
    "        return {\n            \"success\": True,\n            \"message\": \"Document deleted successfully\",\n        }",
    "        logger.info(\"Document deleted: id=%d, user=%d\", document_id, user_id)\n\n"
    "        try:\n"
    "            from services.notification_service import create_notification\n"
    "            create_notification(\n"
    "                doc_user_id,\n"
    "                title=\"Document deleted\",\n"
    "                message=doc_filename,\n"
    "                type=\"document\",\n"
    "                data={\"document_id\": doc_id},\n"
    "                dedupe_key=f\"delete:{doc_user_id}:{doc_id}\",\n"
    "            )\n"
    "        except Exception:\n"
    "            logger.exception(\"Failed to create delete notification for document %d\", doc_id)\n\n"
    "        return {\n            \"success\": True,\n            \"message\": \"Document deleted successfully\",\n        }",
    1,
)

open(p, 'w').write(s)
print("document_service edits applied")
