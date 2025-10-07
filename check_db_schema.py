#!/usr/bin/env python
"""
Check database schema for payroll_salary table
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings_ci')
django.setup()

from django.db import connection

def check_table_schema():
    """Check the actual schema of payroll_salary table."""
    with connection.cursor() as cursor:
        # Get table columns
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'payroll_salary'
            ORDER BY ordinal_position;
        """)

        columns = cursor.fetchall()

        print("=== payroll_salary table schema ===")
        print(f"{'Column':<25} {'Type':<15} {'Nullable':<10} {'Default'}")
        print("-" * 70)

        for col in columns:
            print(f"{col[0]:<25} {col[1]:<15} {col[2]:<10} {col[3] or ''}")

        # Check if is_active exists
        is_active_exists = any(col[0] == 'is_active' for col in columns)
        print(f"\nis_active column exists: {is_active_exists}")

        return is_active_exists

if __name__ == '__main__':
    try:
        check_table_schema()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()