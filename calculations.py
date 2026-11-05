
import sqlite3
import pandas as pd


def get_business_summary():
    conn = sqlite3.connect("dukasense.db")

    sales = pd.read_sql_query(
        "SELECT * FROM sales", conn
    )

    expenses = pd.read_sql_query(
        "SELECT * FROM expenses", conn
    )

    credit = pd.read_sql_query(
        "SELECT * FROM credit", conn
    )

    conn.close()

    revenue = (sales["quantity"] * sales["unit_price"]).sum() if not sales.empty else 0

    collected = sales["amount_paid"].sum() if not sales.empty else 0

    total_expenses = expenses["amount"].sum() if not expenses.empty else 0

    outstanding_credit = (
        (credit["amount"] - credit["amount_paid"]).clip(lower=0).sum()
        if not credit.empty else 0
    )

    return {
        "revenue": revenue,
        "collected": collected,
        "expenses": total_expenses,
        "estimated_profit_before_stock_costs": revenue - total_expenses,
        "outstanding_credit": outstanding_credit
    }
