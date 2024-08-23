from fiscal_network import app
from waitress import serve

if __name__ == "__main__":
    host = '0.0.0.0'
    port = 5000
    print(f"Запуск сервера на http://{host}:{port}")
    serve(app, host=host, port=port)
