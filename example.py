# -*- coding: utf-8 -*-

from shtrihmfr.kkt import KKT, KktError, ConnectionError

def process_receipt(com_port, bod, total_sum, payment_type, discounts):
    """
    Обрабатывает чек с учетом скидок и закрывает его.
    
    :param com_port: Название COM порта (например, 'COM8')
    :param bod: Скорость соединения (baud rate) (например, 115200)
    :param total_sum: Общая сумма чека
    :param payment_type: Тип оплаты (1 - наличные, 2 - безналичные)
    :param discounts: Список скидок, каждая из которых представляет собой словарь с ключами 'name', 'value', и 'count'
    """
    try:
        # Создаем объект ККТ
        fr = KKT(port=com_port, bod=bod)

        # Обрабатываем каждую скидку
        for discount in discounts:
            name = discount['name']
            price = discount['value']
            count = discount.get('count', 1)
            try:
                result = fr.x80(count=count, price=price, text=name, department=1, taxes=[0, 0, 0, 0])
                print(f"Продажа '{name}' {count} шт. успешно добавлена. Результат: {result}")
            except (ConnectionError, KktError) as e:
                print(f"Ошибка при продаже '{name}': {str(e)}")
                return

        # Закрываем чек
        payment_mapping = {
            1: [total_sum, 0, 0, 0],
            2: [0, total_sum, 0, 0]
        }
        payment_details = payment_mapping.get(payment_type, [0, 0, 0, 0])
        
        try:
            result = fr.x85(summs=payment_details, taxes=[1, 0, 0, 0], text="Билет")
            print(f"Чек успешно закрыт. Результат: {result}")
        except (ConnectionError, KktError) as e:
            print(f"Ошибка при закрытии чека: {str(e)}")
            return

    except (ConnectionError, KktError) as e:
        print("Ошибка:")
        print(e)  # Выводим ошибку без форматирования

def x_report(com_port, bod):
    try:
        # Создаем объект ККТ
        fr = KKT(port=com_port, bod=bod)
        fr.x40()
    except (ConnectionError, KktError) as e:
                print(f"Ошибка при снятий суточного отчета без гашения: {str(e)}")
                return
    
def z_report(com_port, bod):
    try:
        # Создаем объект ККТ
        fr = KKT(port=com_port, bod=bod)
        fr.x41()
    except (ConnectionError, KktError) as e:
                print(f"Ошибка при снятий суточного отчета с гашением: {str(e)}")
                return


if __name__ == '__main__':
    com_port = 'COM8'
    bod = 115200
    total_sum = 500.0
    payment_type = 2
    discounts = [
        {"name": "Скидка студент", "value": 100.0, "count": 1},
        {"name": "Скидка пенсионер", "value": 200.0, "count": 2}
    ]

    process_receipt(com_port=com_port, bod=bod, total_sum=total_sum, payment_type=payment_type, discounts=discounts)
    # x_report(com_port=com_port, bod=bod)
