
import sqlite3
import uuid
from datetime import datetime, date
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from database import create_tables, connect
from backup import create_backup_bytes, restore_database


# ==================================================
# PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="DukaSense",
    page_icon="🛒",
    layout="wide"
)

create_tables()


# ==================================================
# PERMANENT SETTINGS
# ==================================================

def create_settings_table():
    conn = connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
    """)

    conn.execute("""
        INSERT OR IGNORE INTO settings
        (setting_key, setting_value)
        VALUES ('business_name', 'My Business')
    """)

    conn.commit()
    conn.close()


def get_business_name():
    conn = connect()

    result = conn.execute("""
        SELECT setting_value
        FROM settings
        WHERE setting_key = 'business_name'
    """).fetchone()

    conn.close()

    return result[0] if result else "My Business"


def save_business_name(name):
    conn = connect()

    conn.execute("""
        INSERT OR REPLACE INTO settings
        (setting_key, setting_value)
        VALUES ('business_name', ?)
    """, (name.strip(),))

    conn.commit()
    conn.close()


create_settings_table()


# ==================================================
# SESSION STATE
# ==================================================

if "cart" not in st.session_state:
    st.session_state.cart = {}


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def money(value):
    return f"KSh {value:,.2f}"


def get_products():
    conn = connect()

    products = pd.read_sql_query(
        "SELECT * FROM products ORDER BY name",
        conn
    )

    conn.close()

    return products


# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.title("🛒 DukaSense")
st.sidebar.caption("Simple business management")

page = st.sidebar.radio(
    "Choose a section",
    [
        "Dashboard",
        "Stock Management",
        "Checkout",
        "Transactions",
        "Daily Reports",
        "Expenses",
        "Business Settings",
        "Backup & Restore"
    ]
)


# ==================================================
# DASHBOARD
# ==================================================

if page == "Dashboard":

    st.title("Business Dashboard")
    st.write("Your business performance at a glance.")

    conn = connect()

    sales = pd.read_sql_query(
        "SELECT * FROM sales",
        conn
    )

    expenses = pd.read_sql_query(
        "SELECT * FROM expenses",
        conn
    )

    products = pd.read_sql_query(
        "SELECT * FROM products",
        conn
    )

    conn.close()

    revenue = sales["total"].sum() if not sales.empty else 0

    collected = (
        (sales["amount_received"] - sales["change_due"]).sum()
        if not sales.empty else 0
    )

    gross_profit = (
        (
            sales["total"]
            - sales["quantity"] * sales["unit_cost"]
        ).sum()
        if not sales.empty else 0
    )

    total_expenses = (
        expenses["amount"].sum()
        if not expenses.empty else 0
    )

    estimated_profit = gross_profit - total_expenses

    stock_value = (
        (products["quantity"] * products["buying_price"]).sum()
        if not products.empty else 0
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Sales Revenue", money(revenue))
    col2.metric("Money Collected", money(collected))
    col3.metric("Expenses", money(total_expenses))

    col4, col5, col6 = st.columns(3)

    col4.metric("Gross Profit", money(gross_profit))
    col5.metric("Estimated Profit", money(estimated_profit))
    col6.metric("Stock Value", money(stock_value))

    st.divider()

    st.subheader("Stock Alerts")

    if products.empty:

        st.info("No products registered yet.")

    else:

        low_stock = products[
            products["quantity"] <= 5
        ]

        if low_stock.empty:

            st.success("No low-stock alerts.")

        else:

            st.warning("Some products have low stock.")

            st.dataframe(
                low_stock[
                    ["name", "quantity", "selling_price"]
                ],
                use_container_width=True,
                hide_index=True
            )

    st.divider()

    st.subheader("Recent Sales")

    if sales.empty:

        st.info("No sales recorded yet.")

    else:

        recent_sales = sales.sort_values(
            "id",
            ascending=False
        ).head(5)

        st.dataframe(
            recent_sales[
                [
                    "date",
                    "product_id",
                    "quantity",
                    "total",
                    "payment_method"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )


# ==================================================
# STOCK MANAGEMENT
# ==================================================

elif page == "Stock Management":

    st.title("Stock Management")

    tab1, tab2 = st.tabs(
        ["Register New Product", "Restock Existing Product"]
    )

    with tab1:

        st.subheader("Register a product")

        with st.form("register_product_form"):

            product_name = st.text_input("Product name")

            quantity = st.number_input(
                "Quantity in stock",
                min_value=0.01,
                value=1.0,
                step=1.0
            )

            buying_price = st.number_input(
                "Buying price per unit (KSh)",
                min_value=0.01,
                value=10.0,
                step=1.0
            )

            selling_price = st.number_input(
                "Selling price per unit (KSh)",
                min_value=0.01,
                value=15.0,
                step=1.0
            )

            register = st.form_submit_button("Register Product")

            if register:

                if not product_name.strip():

                    st.error("Enter a product name.")

                elif selling_price < buying_price:

                    st.warning(
                        "Your selling price is below your buying price."
                    )

                else:

                    conn = connect()

                    try:

                        cursor = conn.cursor()

                        cursor.execute(
                            """
                            INSERT INTO products
                            (name, quantity, buying_price, selling_price)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                product_name.strip(),
                                quantity,
                                buying_price,
                                selling_price
                            )
                        )

                        product_id = cursor.lastrowid

                        cursor.execute(
                            """
                            INSERT INTO stock_purchases
                            (product_id, quantity, buying_price, date)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                product_id,
                                quantity,
                                buying_price,
                                datetime.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            )
                        )

                        conn.commit()

                        st.success(
                            f"{product_name} registered successfully."
                        )

                    except sqlite3.IntegrityError:

                        st.error(
                            "This product already exists. "
                            "Use the restock section instead."
                        )

                    finally:

                        conn.close()

    with tab2:

        products = get_products()

        if products.empty:

            st.info("Register a product first.")

        else:

            product_options = {
                row["name"]: row
                for _, row in products.iterrows()
            }

            selected_name = st.selectbox(
                "Choose product",
                list(product_options.keys())
            )

            selected_product = product_options[selected_name]

            st.write(
                f"Current quantity: **{selected_product['quantity']}**"
            )

            with st.form("restock_form"):

                new_quantity = st.number_input(
                    "Quantity purchased",
                    min_value=0.01,
                    value=1.0,
                    step=1.0
                )

                new_buying_price = st.number_input(
                    "New buying price per unit (KSh)",
                    min_value=0.01,
                    value=float(selected_product["buying_price"]),
                    step=1.0
                )

                new_selling_price = st.number_input(
                    "Selling price per unit (KSh)",
                    min_value=0.01,
                    value=float(selected_product["selling_price"]),
                    step=1.0
                )

                restock = st.form_submit_button(
                    "Record Stock Purchase"
                )

                if restock:

                    old_quantity = float(
                        selected_product["quantity"]
                    )

                    old_average = float(
                        selected_product["buying_price"]
                    )

                    total_quantity = old_quantity + new_quantity

                    if old_quantity == 0:

                        average_cost = new_buying_price

                    else:

                        average_cost = (
                            (
                                old_quantity * old_average
                                + new_quantity * new_buying_price
                            ) / total_quantity
                        )

                    conn = connect()

                    try:

                        cursor = conn.cursor()

                        cursor.execute(
                            """
                            UPDATE products
                            SET quantity = ?,
                                buying_price = ?,
                                selling_price = ?
                            WHERE id = ?
                            """,
                            (
                                total_quantity,
                                average_cost,
                                new_selling_price,
                                int(selected_product["id"])
                            )
                        )

                        cursor.execute(
                            """
                            INSERT INTO stock_purchases
                            (product_id, quantity, buying_price, date)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                int(selected_product["id"]),
                                new_quantity,
                                new_buying_price,
                                datetime.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            )
                        )

                        conn.commit()

                        st.success(
                            "Stock restocked successfully."
                        )

                    finally:

                        conn.close()

    st.divider()

    st.subheader("Current Stock")

    products = get_products()

    if products.empty:

        st.info("No products registered yet.")

    else:

        st.dataframe(
            products[
                [
                    "name",
                    "quantity",
                    "buying_price",
                    "selling_price"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )


# ==================================================
# CHECKOUT
# ==================================================

elif page == "Checkout":

    st.title("Customer Checkout")

    products = get_products()

    if products.empty:

        st.warning(
            "Register products before recording sales."
        )

    else:

        st.subheader("1. Add products")

        available_products = products[
            products["quantity"] > 0
        ]

        if available_products.empty:

            st.warning("No products currently in stock.")

        else:

            product_options = {
                row["name"]: row
                for _, row in available_products.iterrows()
            }

            selected_name = st.selectbox(
                "Choose product",
                list(product_options.keys())
            )

            selected_product = product_options[selected_name]

            st.write(
                f"Available stock: **{selected_product['quantity']}**"
            )

            item_quantity = st.number_input(
                "Quantity customer wants",
                min_value=0.01,
                max_value=float(selected_product["quantity"]),
                value=1.0,
                step=1.0
            )

            if st.button("Add to Basket"):

                product_id = int(selected_product["id"])

                existing_quantity = (
                    st.session_state.cart.get(product_id, 0)
                )

                requested_quantity = (
                    existing_quantity + item_quantity
                )

                if requested_quantity > selected_product["quantity"]:

                    st.error("Not enough stock.")

                else:

                    st.session_state.cart[product_id] = (
                        requested_quantity
                    )

                    st.success(
                        f"{selected_name} added to basket."
                    )

                    st.rerun()

        st.divider()

        st.subheader("2. Customer's Basket")

        current_products = get_products()

        cart_rows = []

        for product_id, quantity in (
            st.session_state.cart.items()
        ):

            matching = current_products[
                current_products["id"] == product_id
            ]

            if matching.empty:
                continue

            product = matching.iloc[0]

            cart_rows.append(
                {
                    "Product": product["name"],
                    "Quantity": quantity,
                    "Unit Price": float(product["selling_price"]),
                    "Total": (
                        quantity * float(product["selling_price"])
                    )
                }
            )

        if not cart_rows:

            st.info("Basket is empty.")

        else:

            cart_df = pd.DataFrame(cart_rows)

            total = cart_df["Total"].sum()

            st.dataframe(
                cart_df,
                use_container_width=True,
                hide_index=True
            )

            st.subheader(f"Total Bill: {money(total)}")

            st.write("Remove an item if necessary:")

            for product_id in list(
                st.session_state.cart.keys()
            ):

                matching = current_products[
                    current_products["id"] == product_id
                ]

                if not matching.empty:

                    product_name = matching.iloc[0]["name"]

                    if st.button(
                        f"Remove {product_name}",
                        key=f"remove_{product_id}"
                    ):

                        del st.session_state.cart[product_id]
                        st.rerun()

            if st.button("Clear Entire Basket"):

                st.session_state.cart = {}
                st.rerun()

            st.divider()

            st.subheader("3. Receive Payment")

            payment_method = st.radio(
                "Payment method",
                ["Cash", "M-Pesa"],
                horizontal=True
            )

            amount_received = st.number_input(
                "Amount customer gives (KSh)",
                min_value=0.0,
                value=float(total),
                step=10.0
            )

            change = amount_received - total

            if amount_received < total:

                st.warning(
                    f"Customer still owes "
                    f"{money(total - amount_received)}."
                )

            elif payment_method == "Cash":

                st.success(
                    f"Give customer change: {money(change)}"
                )

            elif change > 0:

                st.warning(
                    "M-Pesa overpayment needs separate refund handling."
                )

            if st.button(
                "Complete Sale",
                type="primary",
                disabled=not st.session_state.cart
            ):

                if amount_received < total:

                    st.error(
                        "Customer has not paid the full amount."
                    )

                elif payment_method == "M-Pesa" and change > 0:

                    st.error(
                        "Enter the exact M-Pesa amount received."
                    )

                else:

                    conn = connect()

                    try:

                        cursor = conn.cursor()

                        fresh_items = []
                        actual_total = 0

                        for product_id, quantity in (
                            st.session_state.cart.items()
                        ):

                            product = cursor.execute(
                                """
                                SELECT id, name, quantity,
                                       buying_price, selling_price
                                FROM products
                                WHERE id = ?
                                """,
                                (product_id,)
                            ).fetchone()

                            if product is None:

                                raise ValueError(
                                    "A product no longer exists."
                                )

                            (
                                pid,
                                name,
                                available,
                                buying_price,
                                selling_price
                            ) = product

                            if quantity > available:

                                raise ValueError(
                                    f"Not enough stock for {name}."
                                )

                            line_total = quantity * selling_price
                            actual_total += line_total

                            fresh_items.append(
                                {
                                    "id": pid,
                                    "name": name,
                                    "quantity": quantity,
                                    "buying_price": buying_price,
                                    "selling_price": selling_price,
                                    "line_total": line_total
                                }
                            )

                        if abs(actual_total - total) > 0.001:

                            raise ValueError(
                                "A product price changed. "
                                "Review the basket."
                            )

                        receipt_id = uuid.uuid4().hex[:10].upper()

                        sale_date = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                        for index, item in enumerate(fresh_items):

                            cursor.execute(
                                """
                                UPDATE products
                                SET quantity = quantity - ?
                                WHERE id = ? AND quantity >= ?
                                """,
                                (
                                    item["quantity"],
                                    item["id"],
                                    item["quantity"]
                                )
                            )

                            if cursor.rowcount != 1:

                                raise ValueError(
                                    f"Stock update failed for "
                                    f"{item['name']}."
                                )

                            received_for_line = (
                                amount_received if index == 0 else 0
                            )

                            change_for_line = (
                                amount_received - actual_total
                                if (
                                    index == 0
                                    and payment_method == "Cash"
                                )
                                else 0
                            )

                            cursor.execute(
                                """
                                INSERT INTO sales (
                                    product_id,
                                    quantity,
                                    unit_price,
                                    unit_cost,
                                    total,
                                    amount_received,
                                    change_due,
                                    payment_method,
                                    date,
                                    receipt_id
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    item["id"],
                                    item["quantity"],
                                    item["selling_price"],
                                    item["buying_price"],
                                    item["line_total"],
                                    received_for_line,
                                    change_for_line,
                                    payment_method,
                                    sale_date,
                                    receipt_id
                                )
                            )

                        conn.commit()

                        st.session_state.cart = {}

                        st.success("Sale recorded successfully!")

                        st.write(
                            f"Receipt number: **{receipt_id}**"
                        )

                        st.write(
                            f"Total: **{money(actual_total)}**"
                        )

                        st.rerun()

                    except Exception as error:

                        conn.rollback()

                        st.error(
                            f"Sale could not be completed: {error}"
                        )

                    finally:

                        conn.close()


# ==================================================
# TRANSACTIONS AND RECEIPTS
# ==================================================

elif page == "Transactions":

    st.title("Sales Transactions")

    conn = connect()

    transactions = pd.read_sql_query(
        """
        SELECT
            COALESCE(
                sales.receipt_id,
                'OLD-' || sales.id
            ) AS receipt,

            GROUP_CONCAT(
                products.name || ' x ' ||
                CAST(sales.quantity AS TEXT),
                ', '
            ) AS items,

            SUM(sales.total) AS total,
            SUM(sales.amount_received) AS amount_received,
            SUM(sales.change_due) AS change_due,
            MAX(sales.payment_method) AS payment_method,
            MAX(sales.date) AS date

        FROM sales

        JOIN products
            ON sales.product_id = products.id

        GROUP BY COALESCE(
            sales.receipt_id,
            'OLD-' || sales.id
        )

        ORDER BY MAX(sales.id) DESC
        """,
        conn
    )

    conn.close()

    if transactions.empty:

        st.info("No transactions recorded yet.")

    else:

        st.dataframe(
            transactions,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader("Customer Receipt")

        selected_receipt = st.selectbox(
            "Choose receipt number",
            transactions["receipt"].tolist()
        )

        receipt = transactions[
            transactions["receipt"] == selected_receipt
        ].iloc[0]

        conn = connect()

        receipt_items = pd.read_sql_query(
            """
            SELECT
                products.name,
                sales.quantity,
                sales.unit_price,
                sales.total

            FROM sales

            JOIN products
                ON sales.product_id = products.id

            WHERE COALESCE(
                sales.receipt_id,
                'OLD-' || sales.id
            ) = ?

            ORDER BY sales.id
            """,
            conn,
            params=(selected_receipt,)
        )

        conn.close()

        item_html = ""

        for _, item in receipt_items.iterrows():

            item_html += f"""
                <tr>
                    <td>{escape(str(item['name']))}</td>
                    <td class="center">{item['quantity']:g}</td>
                    <td class="right">{money(item['unit_price'])}</td>
                    <td class="right">{money(item['total'])}</td>
                </tr>
            """

        receipt_document = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">

            <style>

                body {{
                    background: #f1f1f1;
                    color: black;
                    font-family: monospace;
                    padding: 10px;
                }}

                .receipt {{
                    background: white;
                    max-width: 380px;
                    margin: 10px auto;
                    padding: 20px;
                    box-sizing: border-box;
                }}

                h2, .center {{
                    text-align: center;
                }}

                .right {{
                    text-align: right;
                }}

                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 11px;
                }}

                th, td {{
                    padding: 7px 2px;
                    border-bottom: 1px dashed #999;
                }}

                .print-button {{
                    display: block;
                    margin: 15px auto;
                    padding: 12px 25px;
                    background: #1769aa;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 15px;
                    cursor: pointer;
                }}

                @media print {{

                    body {{
                        background: white;
                        padding: 0;
                    }}

                    .receipt {{
                        margin: 0;
                        padding: 5px;
                        max-width: 100%;
                    }}

                    .print-button {{
                        display: none;
                    }}

                    @page {{
                        margin: 8mm;
                    }}
                }}

            </style>
        </head>

        <body>

            <button
                class="print-button"
                onclick="window.print()"
            >
                Print Receipt
            </button>

            <div class="receipt">

                <h2>{escape(get_business_name())}</h2>

                <p class="center">CUSTOMER RECEIPT</p>

                <hr>

                <p>
                    Receipt: {escape(str(receipt['receipt']))}
                </p>

                <p>
                    Date: {escape(str(receipt['date']))}
                </p>

                <hr>

                <table>

                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Qty</th>
                            <th>Price</th>
                            <th>Total</th>
                        </tr>
                    </thead>

                    <tbody>
                        {item_html}
                    </tbody>

                </table>

                <hr>

                <p>
                    Total:
                    <strong>{money(receipt['total'])}</strong>
                </p>

                <p>
                    Payment: {escape(str(receipt['payment_method']))}
                </p>

                <p>
                    Received: {money(receipt['amount_received'])}
                </p>

                <p>
                    Change: {money(receipt['change_due'])}
                </p>

                <hr>

                <p class="center">
                    Thank you for shopping with us!
                </p>

            </div>

        </body>
        </html>
        """

        components.html(
            receipt_document,
            height=650,
            scrolling=True
        )

        st.write(
            f"Total sales: "
            f"**{money(transactions['total'].sum())}**"
        )


# ==================================================
# DAILY SALES REPORTS
# ==================================================

elif page == "Daily Reports":

    st.title("Daily Sales Reports")

    st.write(
        "Review your business performance for any selected date."
    )

    selected_date = st.date_input(
        "Select report date",
        value=date.today()
    )

    date_string = selected_date.strftime("%Y-%m-%d")

    conn = connect()

    daily_sales = pd.read_sql_query(
        """
        SELECT
            sales.*,
            products.name AS product_name
        FROM sales
        JOIN products
            ON sales.product_id = products.id
        WHERE DATE(sales.date) = ?
        ORDER BY sales.id
        """,
        conn,
        params=(date_string,)
    )

    daily_expenses = pd.read_sql_query(
        """
        SELECT *
        FROM expenses
        WHERE DATE(date) = ?
        ORDER BY id
        """,
        conn,
        params=(date_string,)
    )

    conn.close()

    st.divider()

    st.subheader(
        f"Report for {selected_date.strftime('%d %B %Y')}"
    )

    if daily_sales.empty:

        st.info("No sales were recorded on this date.")

    else:

        revenue = daily_sales["total"].sum()

        cash_collected = (
            daily_sales.loc[
                daily_sales["payment_method"] == "Cash",
                "amount_received"
            ].sum()
            -
            daily_sales.loc[
                daily_sales["payment_method"] == "Cash",
                "change_due"
            ].sum()
        )

        mpesa_collected = (
            daily_sales.loc[
                daily_sales["payment_method"] == "M-Pesa",
                "amount_received"
            ].sum()
            -
            daily_sales.loc[
                daily_sales["payment_method"] == "M-Pesa",
                "change_due"
            ].sum()
        )

        gross_profit = (
            daily_sales["total"]
            - (
                daily_sales["quantity"]
                * daily_sales["unit_cost"]
            )
        ).sum()

        receipt_count = daily_sales[
            "receipt_id"
        ].fillna(
            "OLD-" + daily_sales["id"].astype(str)
        ).nunique()

        col1, col2, col3 = st.columns(3)

        col1.metric("Sales Revenue", money(revenue))
        col2.metric("Cash Collected", money(cash_collected))
        col3.metric("M-Pesa Collected", money(mpesa_collected))

        col4, col5, col6 = st.columns(3)

        col4.metric("Gross Profit", money(gross_profit))
        col5.metric("Transactions", f"{receipt_count:,}")
        col6.metric(
            "Items Sold",
            f"{daily_sales['quantity'].sum():,.0f}"
        )

        st.divider()

        st.subheader("Payment Breakdown")

        payment_data = pd.DataFrame({
            "Payment Method": ["Cash", "M-Pesa"],
            "Amount Collected": [
                cash_collected,
                mpesa_collected
            ]
        })

        st.dataframe(
            payment_data,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader("Best-Selling Products")

        best_sellers = (
            daily_sales
            .groupby("product_name", as_index=False)
            .agg(
                quantity_sold=("quantity", "sum"),
                revenue=("total", "sum")
            )
            .sort_values(
                "quantity_sold",
                ascending=False
            )
        )

        best_sellers.columns = [
            "Product",
            "Quantity Sold",
            "Sales Revenue"
        ]

        st.dataframe(
            best_sellers,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader("Sales Details")

        st.dataframe(
            daily_sales[
                [
                    "date",
                    "product_name",
                    "quantity",
                    "unit_price",
                    "total",
                    "payment_method"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    st.subheader("Daily Expenses")

    if daily_expenses.empty:

        st.info("No expenses recorded on this date.")

        total_daily_expenses = 0

    else:

        total_daily_expenses = daily_expenses["amount"].sum()

        st.dataframe(
            daily_expenses[
                ["date", "description", "amount"]
            ],
            use_container_width=True,
            hide_index=True
        )

    st.metric(
        "Total Expenses",
        money(total_daily_expenses)
    )

    st.divider()

    if not daily_sales.empty:

        estimated_daily_profit = (
            gross_profit - total_daily_expenses
        )

        st.subheader("Daily Business Summary")

        st.metric(
            "Estimated Profit After Expenses",
            money(estimated_daily_profit)
        )

        st.caption(
            "This is gross profit from recorded sales minus recorded "
            "expenses. It is an estimate, not a complete accounting "
            "or tax statement."
        )

        report_excel = pd.ExcelWriter(
            "daily_sales_report.xlsx",
            engine="openpyxl"
        )

        daily_sales.to_excel(
            report_excel,
            sheet_name="Sales",
            index=False
        )

        best_sellers.to_excel(
            report_excel,
            sheet_name="Best Sellers",
            index=False
        )

        daily_expenses.to_excel(
            report_excel,
            sheet_name="Expenses",
            index=False
        )

        report_excel.close()

        with open("daily_sales_report.xlsx", "rb") as file:

            st.download_button(
                label="Download Daily Report (Excel)",
                data=file,
                file_name=f"dukasense_report_{date_string}.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )
            )

    else:

        st.info(
            "Record sales to generate a daily sales report."
        )


# ==================================================
# EXPENSES
# ==================================================

elif page == "Expenses":

    st.title("Business Expenses")

    with st.form("expense_form"):

        description = st.text_input(
            "What was the expense for?"
        )

        amount = st.number_input(
            "Amount (KSh)",
            min_value=0.01,
            value=100.0,
            step=10.0
        )

        submit_expense = st.form_submit_button(
            "Record Expense"
        )

        if submit_expense:

            if not description.strip():

                st.error("Enter an expense description.")

            else:

                conn = connect()

                conn.execute(
                    """
                    INSERT INTO expenses
                    (date, description, amount)
                    VALUES (?, ?, ?)
                    """,
                    (
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        description.strip(),
                        amount
                    )
                )

                conn.commit()
                conn.close()

                st.success("Expense recorded successfully.")

                st.rerun()

    st.divider()

    st.subheader("Expense History")

    conn = connect()

    expense_history = pd.read_sql_query(
        """
        SELECT date, description, amount
        FROM expenses
        ORDER BY id DESC
        """,
        conn
    )

    conn.close()

    if expense_history.empty:

        st.info("No expenses recorded yet.")

    else:

        st.dataframe(
            expense_history,
            use_container_width=True,
            hide_index=True
        )

        st.subheader(
            f"Total Expenses: "
            f"{money(expense_history['amount'].sum())}"
        )


# ==================================================
# BUSINESS SETTINGS
# ==================================================

elif page == "Business Settings":

    st.title("Business Settings")

    st.write(
        "Set the business name displayed on customer receipts."
    )

    with st.form("business_settings_form"):

        business_name = st.text_input(
            "Business name",
            value=get_business_name()
        )

        save_settings = st.form_submit_button(
            "Save Settings"
        )

        if save_settings:

            if not business_name.strip():

                st.error("Enter a business name.")

            else:

                save_business_name(business_name)

                st.success(
                    "Business name saved permanently."
                )


# ==================================================
# BACKUP AND RESTORE
# ==================================================

elif page == "Backup & Restore":

    st.title("Database Backup & Restore")

    st.write(
        "Protect your business records by downloading "
        "a backup of your DukaSense database."
    )

    st.subheader("Download Backup")

    try:

        backup_data = create_backup_bytes()

        st.download_button(
            label="Download Database Backup",
            data=backup_data,
            file_name=f"dukasense_backup_{date.today()}.db",
            mime="application/octet-stream"
        )

        st.caption(
            "This backup includes your products, stock purchases, "
            "sales, expenses and business settings."
        )

    except Exception as error:

        st.error(f"Backup failed: {error}")

    st.divider()

    st.subheader("Restore Previous Backup")

    st.warning(
        "Restoring replaces your current business records. "
        "Download a backup of your current database first."
    )

    uploaded_backup = st.file_uploader(
        "Upload a DukaSense backup file",
        type=["db"]
    )

    confirm_restore = st.checkbox(
        "I understand that restoring replaces my current records."
    )

    if st.button(
        "Restore Database",
        type="primary",
        disabled=(
            uploaded_backup is None or not confirm_restore
        )
    ):

        try:

            restore_database(uploaded_backup.getvalue())

            st.success(
                "Database restored successfully. "
                "Refresh the application to see your restored records."
            )

            st.session_state.cart = {}

        except Exception as error:

            st.error(f"Restore failed: {error}")
