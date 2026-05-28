EMAIL_FAILURE_NOTIFICATION = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Failure Notification</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f6f8;
            padding: 20px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: #fff;
            border-radius: 10px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            padding: 25px;
        }
        h2 {
            margin-top: 0;
            color: #0066cc;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 8px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 10px 14px;
            text-align: left;
            font-size: 14px;
            border: 1px solid #e0e0e0;
        }
        th {
            background: #f0f4f9;
            font-weight: 600;
        }
        td {
            background: #fff;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        .status {
            font-weight: bold;
            color: #d9534f; /* red for failure */
        }
        a {
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }
        a:hover {
            text-decoration: underline;
        }
        .note {
            font-size: 12px;
            color: #666;
            margin-top: 20px;
            border-top: 1px solid #eee;
            padding-top: 8px;
        }
    </style>
</head>
<body>
<div class="container">
    <h2>⚠ Email Failure Notification</h2>

    <p>Hi Team,</p>
    <p>
        We encountered an error while processing an incoming email. 
        The issue occurred during the <strong>{failed_process}</strong> phase, 
        <em>{failure_reason}</em>. The email could not be processed successfully and 
        is currently marked as <span class="status">{email_status}</span>.
    </p>
    <p>Please review the details below and take the necessary steps to resolve the issue.</p>

    <h3>Email Failure Details – AssistCX</h3>
    <table>
        <tr>
            <th>Field</th>
            <th>Description</th>
        </tr>
        <tr>
            <td>Sender Email</td>
            <td>{sender_email}</td>
        </tr>
        <tr>
            <td>Mailbox Email</td>
            <td>{mailbox_email}</td>
        </tr>
        <tr>
            <td>Mailbox Folder</td>
            <td>{mailbox_folder}</td>
        </tr>
        <tr>
            <td>Email Subject</td>
            <td>{subject}</td>
        </tr>
        <tr>
            <td>Failed During</td>
            <td>{failed_process}</td>
        </tr>
        <tr>
            <td>Received At</td>
            <td>{received_at}</td>
        </tr>
        <tr>
            <td>Email ID</td>
            <td>{email_id}</td>
        </tr>
        <tr>
            <td>Email Status</td>
            <td class="status">{email_status}</td>
        </tr>
        <tr>
            <td>Attachment Name(s)</td>
            <td>{attachment_names}</td>
        </tr>
        <tr>
            <td>Email Link</td>
            <td>{email_link}</td>
        </tr>
    </table>

    <p class="note">
        <strong>Note:</strong> This is a system-generated email. Replies to this message will not be monitored.
    </p>
</div>
</body>
</html>
"""

TASK_FAILURE_NOTIFICATION = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Failure Notification</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f6f8;
            padding: 20px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: #fff;
            border-radius: 10px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            padding: 25px;
        }
        h2 {
            margin-top: 0;
            color: #0066cc;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 8px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 10px 14px;
            text-align: left;
            font-size: 14px;
            border: 1px solid #e0e0e0;
        }
        th {
            background: #f0f4f9;
            font-weight: 600;
        }
        td {
            background: #fff;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        .status {
            font-weight: bold;
            color: #d9534f; /* red for failure */
        }
        a {
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }
        a:hover {
            text-decoration: underline;
        }
        .note {
            font-size: 12px;
            color: #666;
            margin-top: 20px;
            border-top: 1px solid #eee;
            padding-top: 8px;
        }
    </style>
</head>
<body>
<div class="container">
    <h2>⚠ Task Failure Notification</h2>

    <p>Hi Team,</p>
    <p>
        We encountered a task failure while processing an incoming email 
        related to <strong>{assigned_agent}</strong>. 
        The issue occurred during the <strong>{failed_process}</strong> phase, 
        <em>likely due to an error while executing the task</em>.
        The task did not complete and is currently marked as <span class="status">{task_status}</span>.
    </p>
    <p>Please review the details below and take the necessary steps to resolve the issue.</p>

    <h3>Task Details</h3>
    <table>
        <tr>
            <th>Field</th>
            <th>Description</th>
        </tr>
        <tr>
            <td>Sender Email</td>
            <td>{sender_email}</td>
        </tr>
        <tr>
            <td>Mailbox Email</td>
            <td>{mailbox_email}</td>
        </tr>
        <tr>
            <td>Mailbox Folder</td>
            <td>{mailbox_folder}</td>
        </tr>
        <tr>
            <td>Email Subject</td>
            <td>{subject}</td>
        </tr>
        <tr>
            <td>Failed During</td>
            <td>{failed_process}</td>
        </tr>
        <tr>
            <td>Assigned Agent</td>
            <td>{assigned_agent}</td>
        </tr>
        <tr>
            <td>Received At</td>
            <td>{received_at}</td>
        </tr>
        <tr>
            <td>Task ID</td>
            <td>{task_id}</td>
        </tr>
        <tr>
            <td>Task Status</td>
            <td class="status">{task_status}</td>
        </tr>
        <tr>
            <td>Attachment Name(s)</td>
            <td>{attachment_names}</td>
        </tr>
        <tr>
            <td>Task Order</td>
            <td>{task_order}</td>
        </tr>
        <tr>
            <td>Task Link</td>
            <td>{task_link}</td>
        </tr>
    </table>

    <p class="note">
        <strong>Note:</strong> This is a system-generated email. Replies to this message will not be monitored.
    </p>
</div>
</body>
</html>
"""

TASK_NOTIFICATION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
   <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Task Output</title>
      <style>
         body {
         margin: 10px 0px;
         padding: 10px;
         font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
         background-color: #f5f5f7;
         line-height: 1.6;
         color: #333;
         }
         table {
         border-collapse: collapse;
         mso-table-lspace: 0pt;
         mso-table-rspace: 0pt;
         }
         .email-wrapper {
         width: 100%;
         background-color: #f5f5f7;
         padding: 20px 0;
         }
         .email-container {
         width: 100%;
         max-width: 600px;
         background-color: white;
         border-radius: 12px;
         box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
         margin: 0 auto;
         }
         .header-cell {
         padding: 40px 30px 20px 30px;
         text-align: center;
         background-color: white;
         border-radius: 12px 12px 0 0;
         }
         .logo {
         width: 50px;
         height: 50px;
         margin: 0 auto 20px;
         display: block;
         text-align: center;
         }
         .logo img {
         width: 50px;
         height: 50px;
         display: block;
         margin: 0 auto;
         }
         .header-title {
         font-size: 24px;
         font-weight: normal;
         color: #1d1d1f;
         margin: 0;
         padding: 0;
         }
         .summary-cell {
         padding: 0 30px 20px 30px;
         text-align: center;
         }
         .summary-text {
         font-size: 16px;
         color: #1d1d1f;
         font-weight: 700;
         padding: 15px;
         line-height: 30px;
         background-color: #f5f5f7;
         border-radius: 8px;
         border: 1px solid #d2d2d7;
         display: inline-block;
         margin: 0;
         }
         .content-cell {
         padding: 0 30px 30px 30px;
         }
         .timestamp {
         font-size: 15px;
         color: #86868b;
         margin: 0 0 20px 0;
         text-align: center;
         }
         .output-content {
         font-size: 15px;
         color: #1d1d1f;
         line-height: 1.6;
         margin: 0 0 30px 0;
         }
         .button-cell {
         text-align: center;
         padding: 20px 0;
         }
         .continue-btn {
         display: inline-block;
         background-color: #1d1d1f;
         color: white;
         padding: 12px 24px;
         border-radius: 8px;
         text-decoration: none;
         font-size: 15px;
         font-weight: 500;
         border: none;
         cursor: pointer;
         }
         .continue-btn:hover {
         background-color: #000;
         }
         .footer-cell {
         padding: 20px 30px;
         text-align: center;
         border-top: 1px solid #e5e5e7;
         }
         .footer-text {
         color: #86868b;
         font-size: 13px;
         margin: 2px 0;
         }
         /* Mobile Responsive */
         @media only screen and (max-width: 600px) {
         .email-wrapper {
         padding: 10px;
         }
         .email-container {
         border-radius: 8px;
         width: 100% !important;
         }
         .header-cell {
         padding: 30px 20px 20px 20px !important;
         }
         .summary-cell {
         padding: 0 20px 20px 20px !important;
         }
         .summary-text {
         padding: 15px !important;
         }
         .content-cell {
         padding: 0 20px 20px 20px !important;
         }
         .footer-cell {
         padding: 15px 20px !important;
         }
         }
      </style>
   </head>
   <body>
      <table role="presentation" class="email-wrapper" cellpadding="0" cellspacing="0" border="0">
         <tr>
            <td align="center">
               <table role="presentation" class="email-container" cellpadding="0" cellspacing="0" border="0">
                  <!-- Header Section -->
                  <tr>
                     <td class="header-cell">
                        <div class="logo">
                           {assistcx_logo}
                        </div>
                        <h1 class="header-title">{task_name}</h1>
                     </td>
                  </tr>
                  <!-- Summary Box -->
                  <tr>
                     <td class="summary-cell">
                        <div class="summary-text">{task_summary}</div>
                     </td>
                  </tr>
                  <!-- Content Section -->
                  <tr>
                     <td class="content-cell">
                        <div class="output-content">
                           {detailed_output_content}
                        </div>
                     </td>
                  </tr>
                  <!-- Continue Reading Button -->
                  {button_section}
                  <!-- Footer -->
                  <tr>
                     <td align="center">
                        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                           <tr>
                              <!-- left spacing -->
                              <td width="20"></td>
                              <!-- footer content with border -->
                              <td style="border-top:1px solid #e5e5e7; padding:20px 0; text-align:center;">
                                 <p class="footer-text">© 2025 Aexonic Pvt Ltd</p>
                                 <p class="footer-text">This email was generated automatically by your task scheduler</p>
                              </td>
                              <!-- right spacing -->
                              <td width="20"></td>
                           </tr>
                        </table>
                     </td>
                  </tr>
               </table>
            </td>
         </tr>
      </table>
   </body>
</html>
"""

# ==================== Issue Notification (single template for all events) ====================
# Placeholders: issue_heading, issue_intro, issue_highlight, issue_details_rows, issue_link
# issue_highlight can be empty; issue_details_rows is built from (label, value) rows in notification.py

ISSUE_NOTIFICATION_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Issue Notification</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f6f8; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.08); padding: 25px; }
        h2 { margin-top: 0; color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 10px 14px; text-align: left; font-size: 14px; border: 1px solid #e0e0e0; }
        th { background: #f0f4f9; font-weight: 600; }
        td { background: #fff; word-wrap: break-word; overflow-wrap: break-word; }
        .highlight-box { background: #f9f9f9; border-left: 4px solid #17a2b8; padding: 15px; margin: 15px 0; border-radius: 4px; }
        .status-old { color: #6c757d; text-decoration: line-through; }
        .status-new { font-weight: bold; color: #fd7e14; }
        a { color: #0066cc; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
        .note { font-size: 12px; color: #666; margin-top: 20px; border-top: 1px solid #eee; padding-top: 8px; }
    </style>
</head>
<body>
<div class="container">
    <h2>{issue_heading}</h2>
    <p>Hi Team,</p>
    <p>{issue_intro}</p>
    {issue_highlight}
    <h3>Issue Details</h3>
    <table>
        <tr><th>Field</th><th>Value</th></tr>
        {issue_details_rows}
        <tr><td>View Issue</td><td>{issue_link}</td></tr>
    </table>
    <p class="note"><strong>Note:</strong> This is a system-generated email. Replies will not be monitored.</p>
</div>
</body>
</html>
"""

TASK_PAUSED_NOTIFICATION = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Paused Notification</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f6f8;
            padding: 20px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: #fff;
            border-radius: 10px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            padding: 25px;
        }
        h2 {
            margin-top: 0;
            color: #b45309;
            border-bottom: 2px solid #f59e0b;
            padding-bottom: 8px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 10px 14px;
            text-align: left;
            font-size: 14px;
            border: 1px solid #e0e0e0;
        }
        th {
            background: #fffbeb;
            font-weight: 600;
        }
        td {
            background: #fff;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        .status {
            font-weight: bold;
            color: #d97706;
        }
        .review-box {
            background: #fffbeb;
            border-left: 4px solid #f59e0b;
            padding: 12px 16px;
            margin: 16px 0;
            border-radius: 4px;
            font-size: 14px;
        }
        a {
            color: #b45309;
            text-decoration: none;
            font-weight: 500;
        }
        a:hover {
            text-decoration: underline;
        }
        .btn-view-task {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 24px;
            background-color: #b45309;
            color: #ffffff !important;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none !important;
            border-radius: 6px;
        }
        .btn-view-task:hover {
            background-color: #92400e;
            text-decoration: none !important;
        }
        .note {
            font-size: 12px;
            color: #666;
            margin-top: 20px;
            border-top: 1px solid #eee;
            padding-top: 8px;
        }
    </style>
</head>
<body>
<div class="container">
    <h2>⏸ Task Paused — Review Required</h2>

    <p>Hi {reviewer_name},</p>
    <p>
        A task assigned to agent <strong>{agent_name}</strong> has been
        <span class="status">paused</span> and is awaiting your review before it can continue.
    </p>

    <div class="review-box">
        <strong>Review Question:</strong><br/>
        {review_question}
    </div>

    <h3>Task Details</h3>
    <table>
        <tr>
            <th>Field</th>
            <th>Description</th>
        </tr>
        <tr>
            <td>Agent Name</td>
            <td>{agent_name}</td>
        </tr>
        <tr>
            <td>Task Title</td>
            <td>{task_title}</td>
        </tr>
        <tr>
            <td>Task ID</td>
            <td>{task_id}</td>
        </tr>
        <tr>
            <td>Tool Awaiting Review</td>
            <td>{tool_name}</td>
        </tr>
        <tr>
            <td>Review Question</td>
            <td>{review_question}</td>
        </tr>
        <tr>
            <td>Task Status</td>
            <td class="status">{task_status}</td>
        </tr>
        <tr>
            <td>Attachment Name(s)</td>
            <td>{attachment_names}</td>
        </tr>
        <tr>
            <td>Paused At</td>
            <td>{paused_at}</td>
        </tr>
    </table>

    <div style="text-align: center;">
        <a href="{task_url}" class="btn-view-task">View Task</a>
    </div>

    <p class="note">
        <strong>Note:</strong> This is a system-generated email. Replies to this message will not be monitored.
    </p>
</div>
</body>
</html>
"""
