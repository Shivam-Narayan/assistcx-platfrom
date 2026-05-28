chemtrade_bol_schema = {
    "name": "Bill of lading",
    "template_class": "bill_of_lading",
    "description": "Data template containing fields required for bill of lading document",
    "document_instructions": ["Data template containing fields required for bill of lading document"],
    "data_schema": [
        {
            "name": "document_type",
            "description": "Type of document, typically found on top",
        },
        {
            "name": "shipper",
            "description": "Shipper name found in the data",
        },
        {
            "name": "consignee",
            "description": "Consignee name found in the data",
        },
        {"name": "point_of_origin", "description": "Point of origin in the data"},
        {
            "name": "bill_of_lading",
            "description": "Bill of lading number found in the data. The field name can also appear as: 'B/LNUMBER' or 'VL NUMBER' or 'B/L NUMBER' or 'B/L NO.'. Typically 7 digits or longer, and usually starts with 8.",
        },
        {
            "name": "customer_order_number",
            "description": "Customer order number in the data. If you see two order number, then first one is customer order number",
        },
        {
            "name": "order_number",
            "description": "Order number mentioned in the data, usually 4 digits long",
        },
        {"name": "carrier_name", "description": "Carrier name mentioned in the data"},
        {
            "name": "required_ship_date",
            "description": "Required ship date in data. Return output strictly in MM/DD/YYYY format",
        },
        {
            "name": "shipped_date",
            "description": "Shipped date mentioned in the data. It should be be within few days of required_shipped_date value. Return output strictly in MM/DD/YYYY format. If you find a date but few characters are alphabet then try to make the best guess to convert them into numbers",
        },
        {
            "name": "transportation_mode",
            "description": "Transportation mode such as truck, railcar, customer pickup etc.",
        },
        {"name": "vehicle_number", "description": "Vehicle number found in the data"},
        {"name": "routing_info", "description": "Routing info found in the data"},
        {
            "name": "invoice_to_buyer",
            "description": "Invoice to buyer data found in the data",
        },
        {
            "name": "consignee_number",
            "description": "Consignee number mentioned in the data",
        },
        {
            "name": "actual_weight",
            "description": "Actual or net weight value found in the data. Typically NOT a whole number and DOES NOT end with 0, always return the most accurate value. It's usually handwritten.",
        },
        {
            "name": "weight_unit",
            "description": "Unit used for showing the weight in the data.",
        },
        {
            "name": "ticket_number",
            "description": "Ticket number found in the weighing ticket page data. Always present on separate page",
        },
        {
            "name": "outbound_date",
            "description": "Outbound date found in the weighing ticket page data. Return output strictly in MM/DD/YYYY format. Always present on separate page",
        },
        {
            "name": "attachment_file",
            "description": "Attachment file url found in the data. It's usually PDF file.",
        },
    ],
}


chemtrade_invoice_schema = {
    "name": "Vendor invoice",
    "template_class": "vendor_invoice",
    "description": "Data template containing fields required for vendor and supplier invoice",
    "document_instructions": ["Data template containing fields required for vendor and supplier invoice"],
    "data_schema": [
        {
            "name": "document_type",
            "description": "Type of document, typically found on top",
        },
        {
            "name": "invoice_number",
            "description": "Invoice number mentioned in the data",
        },
        {
            "name": "invoice_date",
            "description": "Invoice date found in the data",
        },
        {
            "name": "purchase_order",
            "description": "Purchase order value found in the data. It'll always be a numerical value so make sure to correct any OCR error. Convert slash to numeric 1.",
        },
        {
            "name": "bol_number",
            "description": "Bill of lading number found in the data",
        },
        {
            "name": "vendor_name",
            "description": "Vendor name found in the data",
        },
        {
            "name": "street_1",
            "description": "Street mentioned in Vendor address in the data",
        },
        {
            "name": "street_2",
            "description": "Additional street mentioned in Vendor address in the data",
        },
        {
            "name": "po_box",
            "description": "PO Box number mentioned in Vendor address in the data",
        },
        {
            "name": "postal_code",
            "description": "Postal code mentioned in Vendor address in the data",
        },
        {
            "name": "city",
            "description": "City name mentioned in Vendor address in the data",
        },
        {
            "name": "State",
            "description": "State or province name mentioned in Vendor address in the data",
        },
        {
            "name": "country",
            "description": "Country name mentioned in Vendor address in the data",
        },
        {
            "name": "total_amount",
            "description": "Total amount value found in the data",
        },
        {
            "name": "tax_amount",
            "description": "Tax amount mentioned in the data. Sometimes it also appears as GST or HST.",
        },
        {
            "name": "currency",
            "description": "Amount currency found in the data, return the value in standard currency notation.",
        },
        {
            "name": "payment_terms",
            "description": "Payment terms mentioned in the data, if it's available. Provide a clear and relevant payment term text.",
        },
        {
            "name": "line_items",
            "description": "list of items mentioned in the invoice. Return as list of object container following fields:- item_description: Complete description of line item as mentioned in the data, quantity: Quntity mentioned for the line item, unit_price: Unit price of the line item in the data, amount: Amount mentioned for the line item, currency: currency mentioned for the line item.",
        },
        {
            "name": "attachment_file",
            "description": "Attachment file url found in the data. It's usually PDF file.",
        },
    ],
}

chemtrade_order_schema = {
    "name": "Customer order",
    "template_class": "customer_order",
    "description": "Data template containing fields required for creating customer order",
    "document_instructions": ["Data template containing fields required for for creating customer order"],
    "data_schema": [
        {
            "name": "document_type",
            "description": "Type of document, typically found on top",
        },
        {
            "name": "hybris_ticket_number",
            "description": "Hybris Ticket number found in the data",
        },
        {
            "name": "sold_to_number",
            "description": "Sold To number or customer number found in the data",
        },
        {
            "name": "sold_to_name",
            "description": "Customer or sold-to name found in the data",
        },
        {
            "name": "ship_to_name",
            "description": "Ship to name found in Ship to address in the data, pick single line ship to name. Ignore c/o if found in second line.",
        },
        {
            "name": "ship_to_city",
            "description": "City name mentioned in Customer to ship-to address in the data",
        },
        {
            "name": "ship_to_state",
            "description": "State or province name mentioned in Customer or ship-to address in the data",
        },
        {
            "name": "ship_to_country",
            "description": "Country name mentioned in Customer or ship-to address in the data",
        },
        {
            "name": "ship_to_postal_code",
            "description": "Ship to Postal code mentioned in Ship to address in the data",
        },
        {
            "name": "ship_from_name",
            "description": "Ship from name found in Ship from address in the data",
        },
        {
            "name": "ship_from_city",
            "description": "Ship from City name mentioned in Ship fro  address in the data",
        },
        {
            "name": "ship_from_postal_code",
            "description": "Ship from Postal code mentioned in Ship from address in the data",
        },
        {
            "name": "ship_from_state",
            "description": "State or province name mentioned in Ship from address in the data",
        },
        {
            "name": "delivery_date",
            "description": "Customer Requested delivery date found in the data, return in MM/DD/YYYY format",
        },
        {
            "name": "po_number",
            "description": "Purchase order (PO) Number found in the data",
        },
        {
            "name": "line_items",
            "description": "List of items or material information mentioned in the customer order. Return as list of object container following fields:- customer_material: Customer material number, item_description: Complete description of material or line item as mentioned in the data or email, quantity: Quantity mentioned for the material or line item, unit: unit of measurement found in the line item, item_long_text: any other details or instruction added to line item",
        },
        {
            "name": "email_file",
            "description": "Email file url found in the data. It's usually PDF file.",
        },
        {
            "name": "attachment_file",
            "description": "Attachment file url found in the data. It's usually PDF file.",
        },
    ],
}

invoice_query_template = [
    {
        "name": "invoice_number",
        "description": "Invoice number mentioned in the data",
    },
    {
        "name": "purchase_order",
        "description": "Purchase order value found in the data",
    },
    {
        "name": "bill_of_lading_number",
        "description": "Bill of lading number found in the data",
    },
]
