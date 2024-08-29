import logging
import os
from flask import Flask, request, jsonify
from shtrihmfr.kkt import KKT, KktError, ConnectionError

# Создание папки для логов
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Определение файла для логов
log_file = os.path.join(log_dir, 'error.log')

# Настройка логгирования
logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/sell_tickets/<com_port>', methods=['POST'])
def sell_tickets(com_port):
    data = request.json
    total_sum = data.get('total_sum', 0)
    payment_type = data.get('payment_type', 1)  # 1 for cash, 2 for card by default
    discounts = data.get('discounts', [])
    
    payment_mapping = {
        1: [total_sum, 0, 0, 0],  # Cash payment
        2: [0, total_sum, 0, 0]   # Card payment
    }
    
    payment_details = payment_mapping.get(payment_type, [0, 0, 0, 0])  # Default to all zero if undefined payment type

    try:
        fr = KKT(port=com_port, bod=115200)

        for discount in discounts:
            name = discount['name']
            price = discount['value']
            count = discount.get('count', 1)
            fr.x80(count=count, price=price, text=name, department=1, taxes=[0, 0, 0, 0])
            print(f"Продажа '{name}' в количестве {count} шт. успешно добавлена.")

        # Закрытие чека с определенным способом оплаты
        fr.x85(summs=payment_details, taxes=[1, 0, 0, 0])
        print("Чек успешно закрыт.")
        return jsonify({"success": True, "message": "Чек успешно закрыт."}), 200
    except (ConnectionError, KktError) as e:
        logger.error(f"Ошибка: {e}")
        # Подготовка структурированного JSON ответа об ошибке
        error_response = {
            "code": 500,
            "detail": f"{str(e)}",
        }
        return jsonify(error_response), 500


@app.route('/daily_report_x/<com_port>', methods=['POST'])
def daily_report_x(com_port):
    try:
        fr = KKT(port=com_port, bod=115200)

        fr.x40()
        print("X отчет распечатан.")
        return jsonify({"success": True, "message": "X отчет распечатан."}), 200
    except (ConnectionError, KktError) as e:
        logger.error(f"Ошибка: {e}")
        error_response = {
            "code": 500,
            "detail": f"{str(e)}",
        }
        return jsonify(error_response), 500

@app.route('/daily_report_z/<com_port>', methods=['POST'])
def daily_report_z(com_port):
    try:
        fr = KKT(port=com_port, bod=115200)

        fr.x41()
        print("Z отчет распечатан.")
        return jsonify({"success": True, "message": "Z отчет распечатан."}), 200
    except (ConnectionError, KktError) as e:
        logger.error(f"Ошибка: {e}")
        error_response = {
            "code": 500,
            "detail": f"{str(e)}",
        }
        return jsonify(error_response), 500

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5000)
