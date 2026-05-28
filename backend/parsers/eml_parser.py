# Deprecated: This parser is no longer used in any active code path.
# It was previously wired into attachment.extract_data() for .eml files but had an
# incompatible return shape (list of email info dicts instead of ParsedDocument).
# Kept for reference only. Do not import in new code.

# Custom libraries
from logger import configure_logging

# Default libraries
import email
import re
from typing import Optional, Dict, List

# Installed libraries
from typing_extensions import deprecated
from bs4 import BeautifulSoup


logger = configure_logging(__name__)


@deprecated("EMLParser is no longer used. Do not import in new code.")
class EMLParser:
    """
    A class for parsing and extracting data from email files.
    """

    def __init__(self, file_path):
        self.file_path = file_path

    def _decode_str(self, s) -> Optional[str]:
        decoded_header = email.header.decode_header(s)
        return (
            str(decoded_header[0][0], decoded_header[0][1])
            if decoded_header[0][1]
            else str(decoded_header[0][0])
        )

    def extract_email_data(self) -> Optional[str]:
        """Extract email data from the provided email file."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                raw_email = file.read()

            message = email.message_from_string(raw_email)

            sender = self._decode_str(message.get("From", ""))
            recipients = self._decode_str(message.get("To", ""))
            cc = self._decode_str(message.get("CC", ""))
            subject = self._decode_str(message.get("Subject", ""))
            thread_topic = self._decode_str(message.get("Thread-Topic", ""))

            body = ""
            for part in message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if (
                    "text/plain" in content_type
                    and "attachment" not in content_disposition
                ):
                    body = part.get_payload(decode=True).decode()
                    break
                elif (
                    "text/html" in content_type
                    and "attachment" not in content_disposition
                ):
                    body = part.get_payload(decode=True).decode()
                    soup = BeautifulSoup(body, "html.parser")
                    body = soup.get_text(separator=" ")
                    break

            reconstructed_email = (
                f"From: {sender}\nTo: {recipients}\nCC: {cc}\n"
                f"Subject: {subject}\nThread-Topic: {thread_topic}\n\n{body.strip()}"
            )
            return reconstructed_email

        except Exception as e:
            logger.error("Error occurred during email extraction: %s", e)
            return None

    def _extract_emails_from_text(self, text) -> Optional[List[str]]:
        try:
            emails = re.split(r"(?m)^From:", text)
            return [e.strip() for e in emails if e.strip()]
        except Exception as e:
            logger.error("Error occurred while extracting emails from text: %s", e)
            return []

    def _extract_email_info(self, email_list) -> Optional[List[Dict]]:
        result = []
        for email_text in email_list:
            try:
                email_text = email_text.lower()
                sender_email = email_text[
                    email_text.find("<") + 1 : email_text.find(">")
                ]
                sender_name = email_text[: email_text.find("<")].strip()

                to_index = email_text.find("to: ")
                cc_index = email_text.find("cc: ")
                subject_index = email_text.find("subject: ")

                to_data = email_text[to_index + 4 : cc_index].strip()
                recepient_name = to_data[: to_data.find("<")].strip()
                recepient_email = to_data[to_data.find("<") + 1 : to_data.find(">")]

                subject_end_index = email_text.find("\n", subject_index)
                subject = email_text[subject_index + 8 : subject_end_index].strip()

                content_start_index = email_text.find("\n\n") + 2
                content = email_text[content_start_index:].strip()

                email_info = {
                    "subject": subject,
                    "content": content,
                    "senderEmail": sender_email,
                    "senderName": sender_name,
                    "recepientEmail": recepient_email,
                    "recepientName": recepient_name,
                }

                result.append(email_info)
            except Exception as e:
                logger.error("Error occurred while extracting email info: %s", e)

        return result

    def process_email_data(self) -> Optional[List[Dict]]:
        """Process email data by extracting emails and their information."""
        try:
            reconstructed_email = self.extract_email_data()
            email_blocks = self._extract_emails_from_text(reconstructed_email)
            output = self._extract_email_info(email_blocks)
            return output
        except Exception as e:
            logger.error("Error occurred while processing email data: %s", e)
            return []
