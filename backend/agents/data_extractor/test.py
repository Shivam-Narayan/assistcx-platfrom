"""
Test file for Structured Data Extractor.
Run from backend directory: python agents/data_extractor/test.py
"""

import json
import base64
from pathlib import Path
from dotenv import load_dotenv
from agents.data_extractor import StructuredDataExtractor
from langchain_openai import ChatOpenAI

load_dotenv()

# Sample invoice schema
invoice_schema = [
    {
        "name": "invoice_number",
        "description": "Invoice number mentioned in the document",
        "type": "string",
    },
    {
        "name": "invoice_date",
        "description": "Date of the invoice in YYYY-MM-DD format",
        "type": "string",
    },
    {
        "name": "total_amount",
        "description": "Total amount of the invoice",
        "type": "float",
    },
    {
        "name": "billing_address",
        "description": "Billing address details",
        "type": "object",
        "field_schema": [
            {"name": "street", "description": "Street address", "type": "string"},
            {"name": "city", "description": "City name", "type": "string"},
            {"name": "state", "description": "State or province", "type": "string"},
            {
                "name": "zip_code",
                "description": "Postal or ZIP code",
                "type": "string",
            },
        ],
    },
    {
        "name": "line_items",
        "description": "List of items in the invoice",
        "type": "list[object]",
        "field_schema": [
            {
                "name": "item_description",
                "description": "Description of the item",
                "type": "string",
            },
            {
                "name": "quantity",
                "description": "Quantity of the item",
                "type": "float",
            },
            {
                "name": "unit_price",
                "description": "Price per unit",
                "type": "float",
            },
        ],
    },
]

# Sample invoice text
input_text = """
========== Page 1 of 12 ==========
FedEx.

| Invoice Number | Invoice Date | Account Number | Page  |
|----------------|--------------|----------------|-------|
| 9-006-22826    | Sep 25, 2025 | 1246-5617-6    | 1 of 6|

**Billing Address:**
GENERAL CHEMICAL
2500 KINGSHIGHWAY
EAST SAINT LOUIS IL 62201-2446

**Shipping Address:**
GENERAL CHEMICAL
2500 KINGSHIGHWAY
EAST SAINT LOUIS IL 62201-2446

**Invoice Questions?**
Contact FedEx Revenue Services
Phone: 800.622.1147
M-F 7 AM to 8 PM CST
Sa 7 AM to 6 PM CST
Internet: fedex.com

---

**Invoice Summary**

| Service                  | Charges (USD) |
|--------------------------|---------------|
| FedEx Express Services   | $179.32       |
| FedEx Ground Services    | $138.65       |
| FedEx Other Charges      | $0.00         |
| Other Charges            | $61.78        |
| **TOTAL THIS INVOICE**   | **$379.75**   |

You saved $214.94 in discounts this period!
Other discounts may apply.
To pay your FedEx invoice, please go to www.fedex.com/payment. Thank you for using FedEx.

---

**Account Summary as of Sep 25, 2025**

| Description     | Amount (USD) |
|-----------------|--------------|
| Previous Balance| 4,356.99     |
| Payments        | 0.00         |
| Adjustments     | 0.00         |
| New Charges     | 379.75       |
| **New Account Balance** | **$4,736.74** |

Payments not received by Oct 10, 2025 are subject to a late fee.

---

**Invoice Submission**
SAP PO#: 47042037
SAP GR#: 5000506888

**Invoice Submission**
SAP PO#: 47063499
SAP GR#: 5000506889

---

GENERAL CHEMICAL
2500 KINGSHIGHWAY
EAST SAINT LOUIS IL 62201-2446

FedEx
P.O. Box 94515
PALATINE IL 60094-4515

Stephanie Ulman
10/18/2025

63321670007126
1266-01-00-0011557-0003-0032


========== Page 2 of 12 ==========



========== Page 3 of 12 ==========
fisher scientific ACCT# 931154-020 REMIT TO: 13551 COLLECTIONS CTR DR CHICAGO IL 60693

INQUIRE AT: (800) 766-7000 4500 TURNBERRY DRIVE HANOVER PARK IL 60133

D-U-N-S-00-432-1519 FEIN 23-2942737 ORIGINAL INVOICE

PLEASE REFER TO THIS INVOICE NUMBER ON YOUR REMITTANCE

CUSTOMER PURCHASE ORDER NUMBER - RELEASE NUMBER LAB5134 410556858 INV. DATE 09/30/2025 3612032

ORDER NO. D52547389 ACCOUNT NO. 931154-020 CSO CHI F.O.B. SHIPPING POINT ORDER ENTRY DATE 09/11/2025 PAGE 1 DUPLICATE

SOLD TO: ACCOUNTS PAYABLE CHEMTRADE SOLUTIONS LLC 2500 KINGS HIGHWAY EAST SAINT LOUIS IL 62201

SHIP TO: CHEMTRADE SOLUTIONS LLC 2500 KINGS HIGHWAY EAST SAINT LOUIS IL 62201

47056858 5000509075 DUE DATE: 10/30/2025 TERMS: NET 30 DAYS PAYABLE IN U.S. CURRENCY.

INVOICE TYPE: NOR FOR COS

Visit: www.fishersci.com

DESCRIPTION CATALOG NUMBER QUANTITY SHIPPED UNIT PRICE AMOUNT

CALLER-MACKENZIE BROOKS PHONE-618-631-7303

SHIPMENT NBR: 001 FROM: MWD ON: 09/12/2025 ORDERED PART # 08645-6

DESICCATING CABINET 08 645 6 T 1 EA 2,530.00 2,530.00

MERCHANDISE SUBTOTAL 2,530.00

SALES TAX 202.92

SHIPPING-FUEL SURCHARGE T 6.45

TOTAL INVOICE AMOUNT 2,739.37

(T) SUBJECT TO TAX.

For your protection, our company does NOT accept Credit Card Numbers via Fax or Email.

Tell us about your recent customer service experience by completing a short survey. This should take no longer than three minutes. Enter the link below into your browser and enter the passcode shown. http://survey.medallia.com/fishersci PASSCODE: USA-PGH-CS2

E-INVOICE GHTTPS://WWW.E-SCICOM.COM/THERMOFISHER/REGISTER.ASPX

For payment related inquiries, please contact the Email below: NAOMI.MARTIN@THERMOFISHER.COM

Invoice Submission SAP PO# 47056858 SAP GR# 5000509075,

See reverse side for complete terms and conditions or visit http://www.fishersci.com/salesterms

PAST DUE BALANCES ARE SUBJECT TO A FINANCE CHARGE. THIS SHIPMENT WAS DELIVERED IN PERFECT CONDITION AND SIGNED FOR BY THE TRANSPORTATION COMPANY. CONSIGNORS RESPONSIBILITY CEASES UPON DELIVERY OF GOODS TO CARRIER. DO NOT ACCEPT SHIPMENT SHOWING EVIDENCE OF DAMAGE OR SHORTAGE UNTIL AGENT OF CARRIER ENDORSES NOTATION TO THIS EFFECT ON FACE OF TRANSPORTATION RECEIPT. WITHOUT THIS DOCUMENTARY EVIDENCE CLAIM CANNOT BE FILED. SELLER CERTIFIES THAT ALL GOODS (OR SERVICES) COVERED BY THIS INVOICE WERE PRODUCED IN COMPLIANCE WITH ALL APPLICABLE REQUIREMENTS OF SECTIONS 6, 7, AND 12 OF THE FAIR LABOR STANDARDS ACTS OF 1938, AS AMENDED, AND OF THE REGULATIONS AND ORDERS OF THE UNITED STATES DEPARTMENT OF LABOR ISSUED UNDER SECTION 14 THEREOF.

NO CREDIT WILL BE ALLOWED FOR MERCHANDISE RETURNED WITHOUT PRIOR AUTHORIZATION.

THE PRICES SHOWN ON THIS INVOICE ARE NET OF DISCOUNTS PROVIDED AT THE TIME OF PURCHASE. SOME PRODUCTS MAY BE SUBJECT TO ADDITIONAL DISCOUNTS AGREED UPON BETWEEN THE PARTIES.

Stephanie Ulm 012453 1 1 1 0000 0 000


========== Page 4 of 12 ==========



========== Page 5 of 12 ==========
GRAINGER.                               PAGE 1
                                    200332                             ORIGINAL INVOICE
2227 CLARK AVE.                                              GRAINGER ACCOUNT NUMBER             809550940
SAINT LOUIS, MO 63103-2539                                   INVOICE NUMBER                      9670336750
www.grainger.com                                             INVOICE DATE                        10/09/2025
                                                             DUE DATE                            12/08/2025
SHIP TO                                                      AMOUNT DUE                            $320.16
CHEMTRADE ATTN: LAB                                          PO NUMBER:            0047064883
2500 Kingshighway                                            DEPARTMENT:           MCKENZIE BROOKE
East Saint Louis IL 62201-2446                               CALLER:
                                                             CUSTOMER PHONE:       NONE PROVIDED
                                                             ORDER NUMBER:         1563954156
                                                             INCO TERMS:           FOB ORIGIN

BILL TO
GENERAL CHEMICAL
2500 Kingshighway
EAST SAINT LOUIS IL 62201-2446

Pay invoices online at:
www.grainger.com/invoicing
THANK YOU! FEI NUMBER 36-1150280
FOR QUESTIONS ABOUT THIS INVOICE OR ACCOUNT CALL 1-800-472-4643

| PO LINE # | ITEM # | DESCRIPTION                     | QUANTITY | UNIT PRICE | TOTAL  |
|-----------|--------|---------------------------------|----------|------------|--------|
| 30        | 52TA14 | BUNSEN BURNER, MEKER, LP FUEL   | 3        | 99.74      | 299.22 |

Grainger Part Nbr: 52TA14 Customer UOM: MANUFACTURER #: CH0098E
Delivery #6688231768 Date Shipped: 10/09/2025
Carrier: FDX GROUND No: of Pkgs: 1 Wt: 3.420
Trk #: 461077132080

Invoice Submission
SAP PO #: 47064883
SAP GR #: 5000510001

THIS PURCHASE IS GOVERNED EXCLUSIVELY BY GRAINGER'S TERMS OF SALE, INCLUDING: (I)
DISPUTE RESOLUTION REMEDIES, AND (II) CERTAIN WARRANTY AND DAMAGES LIMITATIONS AND
DISCLAIMERS IN EFFECT AT THE TIME OF THE ORDER, WHICH ARE INCORPORATED BY REFERENCE
HEREIN. GRAINGER'S TERMS OF SALE ARE AVAILABLE AT WWW.GRAINGER.COM
PRODUCT RETURN INSTRUCTIONS ARE AVAILABLE AT WWW.GRAINGER.COM/RETURNS

These items are sold for domestic consumption. If exported, purchaser assumes full responsibility for
export controls. Diversion contrary to US law prohibited.

PAY THIS INVOICE - PAYMENT TERMS Net 60 days after inv IN U.S. DOLLARS.
AMOUNT DUE $320.16

PLEASE DETACH THIS PORTION AND RETURN WITH YOUR PAYMENT

BILL TO:                                                REMIT TO:
GENERAL CHEMICAL                                        GRAINGER
2500 Kingshighway                                       DEPT. C-PAY
EAST SAINT LOUIS IL 62201-2446                          PALATINE, IL 60038-0001
UNITED STATES OF AMERICA

Stephanie Ulman

80955094096703367501000003201610002094100000000100000025120830

X                  ACCOUNT NUMBER           DATE             INVOICE NUMBER            AMOUNT DUE
                       809550940           10/09/2025           9670336750                         $320.16

FOR COMMENTS OR CHANGE OF ADDRESS, ENTER INFORMATION ON REVERSE SIDE


========== Page 6 of 12 ==========



========== Page 7 of 12 ==========
ILMO                                     ORIGINAL      INVOICE                PLEASE INC CLUI DE THESE NUMBERS WITH
                                                 240134                           YOUR PAYMENT TO INSURE PRO OP ER CRED IT
                                          47062031                           INVGICE DATE ACCGUNTNUMBER INVOICE.NUMBER
products company                                                            10/09/25 26150         0001596260
                                    20026SDI/
                     ILMO Pro oducts Company 63007030              PLEASE MAKE CHECKS PAYABLE TO
                     1096 Geil Drive                               AND MAIL TO
                     Granite City IL 62040-7171                   ILMO Products Company
                     (618) 931-2138          5000510014 PO Box #6007
                     FAX: (618) 931-2085                          De ec ca at IL 62524 4-600 7
                                                                  (217) 245-2183 FAX: (217) 243-7634
                   B CHEMTRADE CHEMICALS US LLC               S CHEMTRADE CHEMICALS US LLC
                     2500 KINGS HIGHWAY                       P   2500 KIN VC H TWAY
                     FAIRMONT CITY IL 62201                      EAST ST LOUIS MO 62201
                  T                                           T
                                                              O
  ORDER# 0001583317-00 CUS PIO# MCKENZIE                         TERMS Net 45      BRN 000020 INITIALS EB PAGE 1
  ORDERDATE 10/01/25 GAS P/O#                                   SHIPVIA OUR TRUCK SLS 000265 TERR 000317
    SHIPPING ORDER    ITEM        OTY QTY. CYLINDER             DESCRIPTION            UOM PRIUNIT XXXXXXX
     NUMBER DATE                  SHIPD BC SHPD RET'D
                   Location:     |20 **
     15833171008AR UHPT              1 0 1           ARGON, UHP, T, 337 CUFT          CYL 139.10 139.10T
                                                    VOL: 337
     15833171008AC AAWK              I     0 1       ACETYLENE, ATOMIC ABSORPTION,061CYL 306.70 306.70T
                                                     AC 2. 6AA-5 / AC 2.6AA-5N, 390CF
                                                    VOL: 390
     15833171008LP 100               - 0 1           PROPANE, 100LB                   CYL 96.8548 96.85T
                                                    VOL: 100
                                                                 NOTICE
                                                    GO PAPERLESSS! GO GREEN!
                                                    CALL US TODAY AT 217- -2 245-2183
                                                                      Subtotal                         542.65
                                                                Cash/Dep Received                        0.00
                              TOTAL CYLINDERS SHIPPED:        3 RETURNED:       0
Invoice Submission
SAP PO# 47062031
SAP GR# 5000510014,
                              Royea
                                                              Delivery Charge                           50.00
                         So                                                Tax                          43.41
             Stephanie Ulmand
                                         Signed by: new building no signature
    TAXABLE AMOUNT                                                     THAMOUNTOICE
       542.6 5                                                          N CL LUDING TAX                636.06


========== Page 8 of 12 ==========



========== Page 9 of 12 ==========
ILMO                                     ORIGINAL INVOICE                    YOUR PAYMENT TO INSURE PROPE ER CREDIT
                                                a40139
                                                                           INVOICE DATE: ACCOUNTNUMBER INVOICE NUMBER:
                                            47062031
products company                      2002USDIJu3002030                    10/14/25 26150         0001596843
                    ILMO Products Company 500051006 9 AND MAIL TO PLEASE MAKE CHECKS PAYABLE TO
                     1096 Geil Drive
                    Granite City IL 62040-7171                   ILMO Products Company
                     (618) 931-2138                              PO Box #6007
                     FAX:(618) 931-2085                          Decatur IL 62524-6 6007
                                                                 (217) 245-2183 FAX:(217) 243-7634
                  B CHEMTRADE CHEMICALS US LLC               S H CHEMTRADE CHEMICALS US LLC
                  L 2500 KINGS HIGHWAY                           2500 KINGHIGHWAY
                     FAIRMONT CITY IL 62201                      EAST ST LOUIS MO 62201
                                                             T
  ORDERA 0001582269-00 CUSPO LAB5172/47062031                   TERMS Net 45     BAN 000020 INITIALS TC PAGE 1
   ORDER DATE 09/25/25 aas PIO# LAB5172/47062031                SHIPVIA OUR TRUCK SLS 000265 TERR 000020
    SHIPPING ORDE R                     GTY CYL YLINDER        DESCRIPTION            UOM MUNIT      AMOUNT
                       ITEM      SHIPO BO   SHPD RETD                                       PRICE
     NUMBE R DATE
  Item OX UHPT! was deleted (unde. livered). prd: 0 Shp: 0
  Item AIR UZT, was delete d (unde livered). Ord: 0 Shp: 0
                   Location:     |20 **                                              CYL 23.943
     158226910130x T                 0 0 0 2 OXYGEN, T, 337 CUFT                                        0.00T
                                                   VOL:
     15822691013AC AAWK              0 0 0 1 ACETYLENE, ATOMIC ABSORPTION,061CYL 306.70                 0.00T
                                                    AC 2.6AA-5 / AC 2.6AA-5N, 390CF
                                                   VOL:       0
      PICK UP ONLY PLEASE ***
   ** CONTACT UOHN @618-929-0621 BEFORE COMING
     15822691013AR PLC200                     2 2 ARGON, LIQUID, PLC-200,5300 CUFTCYL 413.6249 827.25T
                                                   VOL: 10600
     15822691013AR S                 U 0 0          ARGON, S, 154 CUFT               CYL      89.00     0.00T
                                                   VOL:       0
                                                                  TOTI
                                                   GO PAPERLESS! GO GREEN!
                                                   CALL US TODAY AT 217-245-21 18
                                                                     Subtotal                         827.25
                                                                                                          .00
       Invoice Submission
        SAP PO# 47062031
        SAP GR# 5000510069,
                                                                                                          .00
                                                                           Tax                         66.18
            Stephanie Niman              Signed by :l Andy Carr
     TAXABLE AMOUN NT                                                    AMOUNT
        827.25                                                         THIS INVOICE                   943.43
                                                                        INCLUDING TAX


========== Page 10 of 12 ==========



========== Page 11 of 12 ==========
Date 09/22/2025                                            Mettler-Toledo, LLC
          Customer 300562337             240409
        Page 1 of3                 47054174                                    Columbus, OH 43240-4035
                               2002us011b5a1000                    Accts Receivable (866) 247-8957
                                                                          Email ar@mt.com
                                                                   Sales & Service (800) METTLER
                                  5000506887                                   (800) 638-8537
                                                                           www.mt.com
              Invoice 655438858
             Bil-To I 300562337                                               Sold-To /30056233 7
              Chemtrade Solutions                                             Chemtrade Solutions
             2500 Kings Hwy                                                   2500 Kings Hwy
             East Saint Louis IL 62201-2446                                   East Saint Louis IL 62201-2446
             Ship-To /300562337                                               Remit-To / 300562337
             Chemtrade Solutions                                              METTLER TOLEDO
             2500 Kings Hwy                                                   22670 Network Place
             East Saint Louis IL 62201-2446                                   Chicago IL 60673-1226
                                                                              Please reference your invoice number
                                                                              with your payment.
             Customer Contact
             Stephanie Ulman
             Customer No. 300562337
             Customer PO No. 47054174
             Invoice Data
             Invoice Date           09/22/2025             Contract Duration   09/01/2025 to 08/31/2026
             Invoice No.            655438858              Payment Terms       Due 30 Days from Invoice Date
             Contract No.           184238399
             Item Service Description                                                 Visits
             101 Calibrate Manufacturer Annex
             102 Calibrate ACC
             103 Basic Care
                       Full Preventive Maintenance OnSite EA
                                                Total Net                                         927.03
                                                Totul USD                                        927.03
       Invoice Submission
        SAP PO# 47054174
        SAP GR# 5000506887,
Thank you for your business!                          iduchon
           Bank: JPMorgan Chose                                                      METTLER        TOLEDO
       Account #: 10-84367       Stephanie Ulmap
       Swift Code: CHASUS33
      ABA# ACH: 071 000 013
      ABA# Wire: 021 000 021
      (QESP)43:T004:000005:002:0000: 35629684 2/3


========== Page 12 of 12 ==========
Date 09/22/2025                                            Mettler-Toledo, LLC
          Customer 300562337
        Page 3of3                                                             Columbus, OH 43240-4035
                                                                  Accts Receivable (866) 247-8957
                                                                         Email ar@mt.com
                                                                  Sales & Service (800) METTLER
                                                                              (800) 638-8537
                                                                          www.mt.com
             Invoice 655438858
             Equipments Covered: 1
                Serial Number Model TypeAsset Number System        Cost Center     Reference    Sub-Total
                                                                                    lem/s
             1 C022480650 XPR204                                                 101, 102, 103
                                                Total Net                                        927.03
                                                Total USD                                        927.03
Thank you for your bushess!
          Bank: JPMorgan Chase                                                      METTLER        TOLEDO
      Account #: 10-84367
      Swift Code: CHASUS33
     ABA# ACH: 071 000 013
     ABA# Wire: 021 000 021
     (QESP)43:T004:000005:003:0000: 35629684 3/3
"""


def main():
    """
    Main function to test the data extraction.
    """
    # --- Vision Test Setup ---
    image_path = Path("/Users/Cipher/AssistCX/assistcx-platform/backend/data/inv-6.png")
    image_base64 = None
    mime_type = "image/png"

    try:
        with open(image_path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        print(f"Error reading or encoding image: {e}. Skipping vision test.")
    # --- End Vision Test Setup ---

    # Create data template
    data_template = {
        "name": "Invoice",
        "template_class": "invoice",
        "description": "Data template for invoice extraction",
        "document_instructions": ["Extract invoice details from the provided document"],
        "data_schema": invoice_schema,
    }

    # Initialize LLM directly (avoids needing organization schema and Redis connection)
    llm = ChatOpenAI(model="gpt-4.1", temperature=0, max_retries=1, timeout=120)

    # Initialize the data extractor with LLM instance
    enable_vision = True
    extractor = StructuredDataExtractor(llm=llm, vision=enable_vision)

    # Extract data, passing image data if available
    extracted_data, summary = extractor.extract_data(
        data_template=data_template,
        text_data=input_text,
        image_list=[],
        mime_type=mime_type,
        document_metadata=True,
        field_metadata=True,
        extraction_summary=True,
    )

    # Print the results
    print(f"\n\n=== Extracted Invoice Data ===\n{json.dumps(extracted_data, indent=2)}")
    if summary:
        print(f"\n=== Extraction Summary ===\n{summary}")


if __name__ == "__main__":
    main()
