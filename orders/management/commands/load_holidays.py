from django.core.management.base import BaseCommand
from orders.models import WorkDayCalendar, Employee
from datetime import date, timedelta
import calendar


class Command(BaseCommand):
    help = 'Загрузка календаря праздничных и выходных дней на 2025-2026'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Год для загрузки (по умолчанию 2025 и 2026)',
        )

    def handle(self, *args, **options):
        years = [2025, 2026]
        if options.get('year'):
            years = [options['year']]
        
        # Официальные праздничные дни в России
        holidays = {
            2025: [
                (1, 1),   # Новый год
                (1, 2),   # Новогодние каникулы
                (1, 3),   # Новогодние каникулы
                (1, 4),   # Новогодние каникулы
                (1, 5),   # Новогодние каникулы
                (1, 6),   # Новогодние каникулы
                (1, 7),   # Рождество Христово
                (1, 8),   # Новогодние каникулы
                (2, 23),  # День защитника Отечества
                (3, 8),   # Международный женский день
                (5, 1),   # Праздник Весны и Труда
                (5, 2),   # Перенос с 4 мая
                (5, 3),   # Перенос с 4 мая
                (5, 9),   # День Победы
                (5, 10),  # Перенос с 11 мая
                (6, 12),  # День России
                (11, 3),  # Перенос с 2 ноября
                (11, 4),  # День народного единства
            ],
            2026: [
                (1, 1),   # Новый год
                (1, 2),   # Новогодние каникулы
                (1, 3),   # Новогодние каникулы
                (1, 4),   # Новогодние каникулы
                (1, 5),   # Новогодние каникулы
                (1, 6),   # Новогодние каникулы
                (1, 7),   # Рождество Христово
                (1, 8),   # Новогодние каникулы
                (2, 23),  # День защитника Отечества
                (3, 8),   # Международный женский день
                (5, 1),   # Праздник Весны и Труда
                (5, 9),   # День Победы
                (6, 12),  # День России
                (11, 4),  # День народного единства
            ]
        }
        
        total_created = 0
        total_updated = 0
        
        for year in years:
            self.stdout.write(f'Обработка года {year}...')
            
            # Получаем всех сотрудников
            employees = Employee.objects.all()
            employees_count = employees.count()
            
            if employees_count == 0:
                self.stdout.write(self.style.WARNING(f'Нет сотрудников для обработки'))
                continue
            
            year_created = 0
            year_updated = 0
            
            # Создаем календарь для каждого сотрудника
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            current_date = start_date
            
            while current_date <= end_date:
                # Определяем тип дня
                day_type = 'workday'
                
                # Проверяем выходной (суббота или воскресенье)
                weekday = current_date.weekday()
                if weekday >= 5:  # Суббота (5) или воскресенье (6)
                    day_type = 'weekend'
                
                # Проверяем праздничный день
                if (current_date.month, current_date.day) in holidays.get(year, []):
                    day_type = 'holiday'
                
                # Создаем или обновляем запись для каждого сотрудника
                for employee in employees:
                    calendar_entry, created = WorkDayCalendar.objects.update_or_create(
                        employee=employee,
                        date=current_date,
                        defaults={
                            'day_type': day_type,
                        }
                    )
                    
                    if created:
                        year_created += 1
                        total_created += 1
                    else:
                        year_updated += 1
                        total_updated += 1
                
                current_date += timedelta(days=1)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Год {year}: создано {year_created} записей, обновлено {year_updated} записей '
                    f'(для {employees_count} сотрудников)'
                )
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nВсего обработано: создано {total_created}, обновлено {total_updated} записей календаря'
            )
        )

