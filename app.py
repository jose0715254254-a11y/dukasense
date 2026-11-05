
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
# STOCK AND REORDER SETTINGS
# ==================================================

REORDER_LEVEL = 5
TARGET_STOCK = 10


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
# STOCK CORRECTION AUDIT TABLE
# ==================================================

def create_stock_adjustments_table():

    conn = connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            old_quantity REAL NOT NULL,
            new_quantity REAL NOT NULL,
            difference REAL NOT NULL,
            reason TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    conn.commit()
    conn.close()


create_stock_adjustments_table()


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


def add_reorder_recommendations(products):

    products = products.copy()

    products["recommended_order"] = (
        TARGET_STOCK - products["quantity"]
    ).clip(lower=0)

    products["estimated_reorder_cost"] = (
        products["recommended_order"]
        * products["buying_price"]
    )

    products["stock_status"] = products["quantity"].apply(
        lambda quantity:
            "REORDER NOW"
            if quantity <= REORDER_LEVEL
            else "Sufficient"
    )

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

    # --------------------------------------------------
    # STOCK ALERTS AND REORDER RECOMMENDATIONS
    # --------------------------------------------------

    st.subheader("Stock Alerts & Reorder Recommendations")

    if products.empty:

        st.info("No products registered yet.")

    else:

        low_stock = products[
            products["quantity"] <= REORDER_LEVEL
        ].copy()

        if low_stock.empty:

            st.success("All products have sufficient stock.")

        else:

            low_stock = add_reorder_recommendations(low_stock)

            total_reorder_cost = low_stock[
                "estimated_reorder_cost"
            ].sum()

            total_units_to_order = low_stock[
                "recommended_order"
            ].sum()

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Products Running Low",
                len(low_stock)
            )

            col2.metric(
                "Units to Reorder",
                f"{total_units_to_order:,.2f}"
            )

            col3.metric(
                "Estimated Restocking Cost",
                money(total_reorder_cost)
            )

            st.warning("Some products need restocking.")

            display_alerts = low_stock[
                [
                    "name",
                    "quantity",
                    "buying_price",
                    "recommended_order",
                    "estimated_reorder_cost"
                ]
            ].rename(
                columns={
                    "name": "Product",
                    "quantity": "Remaining Stock",
                    "buying_price": "Buying Price",
                    "recommended_order": "Recommended Order",
                    "estimated_reorder_cost": "Estimated Reorder Cost"
                }
            )

            st.dataframe(
                display_alerts,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "Recommendations aim to bring each low-stock product "
                "up to 10 units. Estimated costs use the current "
                "average buying price."
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

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Register New Product",
            "Restock Existing Product",
            "Stock Purchase History",
            "Stock Corrections"
        ]
    )

    # --------------------------------------------------
    # REGISTER NEW PRODUCT
    # --------------------------------------------------

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

                        conn.rollback()

                        st.error(
                            "This product already exists. "
                            "Use the restock section instead."
                        )

                    finally:

                        conn.close()

    # --------------------------------------------------
    # RESTOCK EXISTING PRODUCT
    # --------------------------------------------------

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
                list(product_options.keys()),
                key="restock_product"
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

                    except Exception as error:

                        conn.rollback()
                        st.error(f"Restocking failed: {error}")

                    finally:

                        conn.close()

    # --------------------------------------------------
    # STOCK PURCHASE HISTORY
    # --------------------------------------------------

    with tab3:

        st.subheader("Stock Purchase History")

        st.write(
            "View every product registration and restocking transaction."
        )

        conn = connect()

        purchase_history = pd.read_sql_query(
            """
            SELECT
                stock_purchases.id,
                products.name AS product_name,
                stock_purchases.quantity,
                stock_purchases.buying_price,
                (
                    stock_purchases.quantity
                    * stock_purchases.buying_price
                ) AS total_cost,
                stock_purchases.date

            FROM stock_purchases

            JOIN products
                ON stock_purchases.product_id = products.id

            ORDER BY stock_purchases.id DESC
            """,
            conn
        )

        conn.close()

        if purchase_history.empty:

            st.info("No stock purchases have been recorded yet.")

        else:

            total_purchase_cost = purchase_history[
                "total_cost"
            ].sum()

            total_units_purchased = purchase_history[
                "quantity"
            ].sum()

            col1, col2 = st.columns(2)

            col1.metric(
                "Total Stock Purchase Cost",
                money(total_purchase_cost)
            )

            col2.metric(
                "Total Units Purchased",
                f"{total_units_purchased:,.2f}"
            )

            st.divider()

            display_history = purchase_history.rename(
                columns={
                    "product_name": "Product",
                    "quantity": "Quantity Purchased",
                    "buying_price": "Buying Price per Unit",
                    "total_cost": "Total Purchase Cost",
                    "date": "Purchase Date"
                }
            )

            display_history = display_history.drop(
                columns=["id"]
            )

            st.dataframe(
                display_history,
                use_container_width=True,
                hide_index=True
            )

    # --------------------------------------------------
    # STOCK CORRECTIONS
    # --------------------------------------------------

    with tab4:

        st.subheader("Correct Physical Stock")

        st.write(
            "Use this section when the actual quantity in your shop "
            "does not match the quantity recorded in DukaSense."
        )

        st.warning(
            "Stock corrections change the current stock quantity. "
            "They do not create a purchase or a sale."
        )

        products = get_products()

        if products.empty:

            st.info("Register products before making stock corrections.")

        else:

            product_options = {
                row["name"]: row
                for _, row in products.iterrows()
            }

            selected_correction_name = st.selectbox(
                "Choose product to correct",
                list(product_options.keys()),
                key="correction_product"
            )

            selected_correction_product = product_options[
                selected_correction_name
            ]

            product_id = int(selected_correction_product["id"])

            current_quantity = float(
                selected_correction_product["quantity"]
            )

            st.metric(
                "Current Recorded Quantity",
                f"{current_quantity:,.2f}"
            )

            with st.form("stock_correction_form"):

                actual_quantity = st.number_input(
                    "Enter actual physical quantity",
                    min_value=0.0,
                    value=current_quantity,
                    step=1.0,
                    key=f"actual_quantity_{product_id}"
                )

                correction_reason = st.selectbox(
                    "Reason for correction",
                    [
                        "Physical stock count",
                        "Damaged goods",
                        "Expired goods",
                        "Theft or loss",
                        "Recording mistake",
                        "Other"
                    ]
                )

                additional_details = st.text_input(
                    "Additional details (optional)"
                )

                save_correction = st.form_submit_button(
                    "Save Stock Correction",
                    type="primary"
                )

                if save_correction:

                    old_quantity = current_quantity
                    new_quantity = float(actual_quantity)

                    difference = new_quantity - old_quantity

                    reason = correction_reason

                    if additional_details.strip():

                        reason += ": " + additional_details.strip()

                    if difference == 0:

                        st.info(
                            "The physical quantity matches the recorded "
                            "quantity. No correction was necessary."
                        )

                    else:

                        conn = connect()

                        try:

                            cursor = conn.cursor()

                            cursor.execute(
                                """
                                UPDATE products
                                SET quantity = ?
                                WHERE id = ?
                                """,
                                (
                                    new_quantity,
                                    product_id
                                )
                            )

                            if cursor.rowcount != 1:

                                raise ValueError(
                                    "The product could not be updated."
                                )

                            cursor.execute(
                                """
                                INSERT INTO stock_adjustments (
                                    product_id,
                                    old_quantity,
                                    new_quantity,
                                    difference,
                                    reason,
                                    date
                                )
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    product_id,
                                    old_quantity,
                                    new_quantity,
                                    difference,
                                    reason,
                                    datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                )
                            )

                            conn.commit()

                            st.success(
                                f"{selected_correction_name} stock "
                                f"corrected successfully."
                            )

                            st.write(
                                f"Previous quantity: **{old_quantity:,.2f}**"
                            )

                            st.write(
                                f"New quantity: **{new_quantity:,.2f}**"
                            )

                            st.write(
                                f"Difference: **{difference:+,.2f}**"
                            )

                        except Exception as error:

                            conn.rollback()

                            st.error(
                                f"Stock correction failed: {error}"
                            )

                        finally:

                            conn.close()

        st.divider()

        st.subheader("Stock Correction History")

        conn = connect()

        adjustment_history = pd.read_sql_query(
            """
            SELECT
                stock_adjustments.id,
                products.name AS product,
                stock_adjustments.old_quantity,
                stock_adjustments.new_quantity,
                stock_adjustments.difference,
                stock_adjustments.reason,
                stock_adjustments.date

            FROM stock_adjustments

            JOIN products
                ON stock_adjustments.product_id = products.id

            ORDER BY stock_adjustments.id DESC
            """,
            conn
        )

        conn.close()

        if adjustment_history.empty:

            st.info("No stock corrections have been recorded yet.")

        else:

            total_corrections = len(adjustment_history)

            increases = adjustment_history[
                adjustment_history["difference"] > 0
            ]

            decreases = adjustment_history[
                adjustment_history["difference"] < 0
            ]

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Total Corrections",
                f"{total_corrections:,}"
            )

            col2.metric(
                "Stock Increases",
                f"{len(increases):,}"
            )

            col3.metric(
                "Stock Decreases",
                f"{len(decreases):,}"
            )

            st.divider()

            display_adjustments = adjustment_history.rename(
                columns={
                    "product": "Product",
                    "old_quantity": "Previous Quantity",
                    "new_quantity": "New Quantity",
                    "difference": "Difference",
                    "reason": "Reason",
                    "date": "Correction Date"
                }
            )

            display_adjustments = display_adjustments.drop(
                columns=["id"]
            )

            st.dataframe(
                display_adjustments,
                use_container_width=True,
                hide_index=True
            )

    # --------------------------------------------------
    # CURRENT STOCK AND REORDER RECOMMENDATIONS
    # --------------------------------------------------

    st.divider()

    st.subheader("Current Stock & Reorder Recommendations")

    products = get_products()

    if products.empty:

        st.info("No products registered yet.")

    else:

        stock_display = add_reorder_recommendations(products)

        display_stock = stock_display.rename(
            columns={
                "name": "Product",
                "quantity": "Current Quantity",
                "buying_price": "Buying Price",
                "selling_price": "Selling Price",
                "stock_status": "Stock Status",
                "recommended_order": "Recommended Order",
                "estimated_reorder_cost": "Estimated Reorder Cost"
            }
        )

        st.dataframe(
            display_stock[
                [
                    "Product",
                    "Current Quantity",
                    "Buying Price",
                    "Selling Price",
                    "Stock Status",
                    "Recommended Order",
                    "Estimated Reorder Cost"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

        total_reorder_cost = stock_display[
            "estimated_reorder_cost"
        ].sum()

        st.metric(
            "Total Estimated Restocking Budget",
            money(total_reorder_cost)
        )

        st.caption(
            "Products with 5 units or fewer are flagged for restocking. "
            "The recommended order brings stock up to 10 units. "
            "These are estimates, not supplier orders."
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

                try:

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

                    st.success("Expense recorded successfully.")

                    st.rerun()

                except Exception as error:

                    conn.rollback()
                    st.error(f"Expense could not be recorded: {error}")

                finally:

                    conn.close()

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
            "stock corrections, sales, expenses and business settings."
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
