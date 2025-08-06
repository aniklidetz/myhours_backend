from django.core.management.base import BaseCommand
from payroll.models import DailyPayrollCalculation
from decimal import Decimal

class Command(BaseCommand):
    help = 'Update total_gross_pay for existing daily payroll calculations'

    def handle(self, *args, **options):
        self.stdout.write("Updating total_gross_pay for existing daily calculations...")
        
        # Find records where total_gross_pay is 0 but total_pay > 0 or employee is monthly
        calculations = DailyPayrollCalculation.objects.filter(total_gross_pay=Decimal('0'))
        
        updated_count = 0
        
        for calc in calculations:
            employee = calc.employee
            calculation_type = employee.salary_info.calculation_type
            
            if calculation_type == 'hourly':
                # For hourly employees: total_gross_pay = total_pay
                calc.total_gross_pay = calc.total_pay
            elif calculation_type == 'monthly':
                # For monthly employees: calculate daily base salary + bonuses
                try:
                    working_days = employee.salary_info.get_working_days_in_month(
                        calc.work_date.year, calc.work_date.month
                    )
                    if working_days > 0:
                        daily_base_salary = employee.salary_info.base_salary / working_days
                        calc.total_gross_pay = daily_base_salary + calc.total_pay
                    else:
                        calc.total_gross_pay = calc.total_pay
                except Exception as e:
                    self.stdout.write(f"Error calculating for {employee.get_full_name()}: {e}")
                    calc.total_gross_pay = calc.total_pay
            else:
                # For other types: use total_pay as fallback
                calc.total_gross_pay = calc.total_pay
            
            calc.save()
            updated_count += 1
            
            self.stdout.write(f"Updated {employee.get_full_name()} - {calc.work_date}: ₪{calc.total_gross_pay}")
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {updated_count} daily calculations')
        )