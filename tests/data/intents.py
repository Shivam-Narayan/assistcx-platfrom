intent_classes = [
    {
        "name": "Invoice query",
        "intent_class": "invoice_query",
        "description": "Email and attachment data indicates that sender may have a query related to invoice details or invoice payment.",
    },
    {
        "name": "Post bill of lading",
        "intent_class": "post_bill_of_lading",
        "description": "Email and attachment data indicates that it's a new bill of lading that needs to be posted. Must have several data fields related to the bill of lading (BOL) such as shipper, consignee, order number etc.",
    },
    {
        "name": "Post invoice",
        "intent_class": "post_invoice",
        "description": "Email and attachment data indicates that it's an invoice or invoices that are due to be posted or due for payment. Must have multiple invoice related data fields such as invoice number, invoice date, amount etc.",
    },
    {
        "name": "Create sales order",
        "intent_class": "create_sales_order",
        "description": "Email and attachment data indicates that it's new sales order or purchase order from the customer. Must have some order or delivery related data.",
    },
]
