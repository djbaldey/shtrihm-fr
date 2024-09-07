# -*- coding: utf-8 -*-
#
#  Copyright 2013 Grigoriy Kramarenko <root@rosix.ru>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
import datetime
import logging
import serial
import time
from shtrihmfr.conf import (
    DEFAULT_ADMIN_PASSWORD, DEFAULT_PASSWORD, DEFAULT_PORT, DEFAULT_BOD,
    CODE_PAGE, MAX_ATTEMPT, MIN_TIMEOUT,
)
from shtrihmfr.protocol import FN_BUGS, BUGS, KKT_FLAGS, FP_FLAGS
from shtrihmfr.utils import (
    int2, int4, int5, int6, int8,
    money2integer, integer2money, count2integer,
    get_control_summ, string2bits,
    digits2string, password_prapare,
    force_bytes
)

logger = logging.getLogger(__name__)

# ASCII
ENQ = bytes([0x05])  # Enquire. Прошу подтверждения.
STX = bytes([0x02])  # Start of Text, начало текста.
ACK = bytes([0x06])  # Acknowledgement. Подтверждаю.
NAK = bytes([0x15])  # Negative Acknowledgment, не подтверждаю.

class KktError(Exception):
    def __init__(self, value):
        if isinstance(value, int):
            self.value = value
            if value in FN_BUGS:
                self.source, self.message = FN_BUGS[value]
            else:
                self.source, self.message = BUGS[value]
            msg = f'{self.source}: {self.message}'
        else:
            msg = value
        super().__init__(msg)

class ConnectionError(KktError):
    pass


class BaseKKT(object):
    """
    Базовый класс включает методы непосредственного общения с
    устройством.

    Общие положения.

    В информационном обмене «Хост – ККТ» хост является главным
    устройством, а ККТ – подчиненным. Поэтому направление
    передачи данных определяется хостом. Физический интерфейс
    «Хост – ККТ» – последовательный интерфейс RS-232С, без линий
    аппаратного квитирования.
    Скорость обмена по интерфейсу RS-232С – 2400, 4800, 9600, 19200,
                                            38400, 57600, 115200.
    При обмене хост и ККТ оперируют сообщениями. Сообщение может
    содержать команду (от хоста) или ответ на команду (от ККТ).
    Формат сообщения:
        Байт 0: признак начала сообщения STX;
        Байт 1: длина сообщения (N) – ДВОИЧНОЕ число.
        В длину сообщения не включаются байты 0, LRC и этот байт;
        Байт 2: код команды или ответа – ДВОИЧНОЕ число;
        Байты 3 – (N + 1): параметры, зависящие от команды
        (могут отсутствовать);
        Байт N + 2 – контрольная сумма сообщения – байт LRC
        – вычисляется поразрядным сложением (XOR) всех байтов
        сообщения (кроме байта 0).

    Сообщение считается принятым, если приняты байт STX
    и байт длины. Сообщение считается принятым корректно, если
    приняты байты сообщения, определенные его байтом длины, и
    байт LRC.
    Каждое принятое сообщение подтверждается передачей
    одного байта (ACK – положительное подтверждение, NAK –
    отрицательное подтверждение).
    Ответ NAK свидетельствует об ошибке интерфейса (данные приняты
    с ошибкой или не распознан STX), но не о неверной команде.
    Отсутствие подтверждения в течение тайм-аута означает, что
    сообщение не принято.
    Если в ответ на сообщение ККТ получен NAK, сообщение не
    повторяется, ККТ ждет уведомления ENQ для повторения ответа.
    После включения питания ККТ ожидает байт запроса – ENQ.
    Ответ от ККТ в виде байта NAK означает, что ККТ находится в
    состоянии ожидания очередной команды;
    ответ ACK означает, что ККТ подготавливает ответное
    сообщение, отсутствии ответа означает отсутствие связи между
    хостом и ККТ.

    По умолчанию устанавливаются следующие параметры порта: 8 бит
    данных, 1 стоп- бит, отсутствует проверка на четность,
    скорость обмена 4800 бод и тайм-аут ожидания каждого байта,
    равный 50 мс. Две последние характеристики обмена могут быть
    изменены командой от хоста. Минимальное время между приемом
    последнего байта сообщения и передачей подтверждения, и между
    приемом ENQ и реакцией на него равно тайм-ауту приема байта.
    Количество повторов при неудачных сеансах связи (нет
    подтверждения после передачи команды, отрицательное
    подтверждение после передачи команды, данные ответа приняты с
    ошибкой или не распознан STX ответа) настраивается при
    реализации программного обеспечения хоста. Коды знаков STX,
    ENQ, ACK и NAK – коды WIN1251.

    """
    error = ''
    port = DEFAULT_PORT
    password = password_prapare(DEFAULT_PASSWORD)
    admin_password = password_prapare(DEFAULT_ADMIN_PASSWORD)
    bod = DEFAULT_BOD
    parity = serial.PARITY_NONE
    stopbits = serial.STOPBITS_ONE
    timeout = 0.7
    writeTimeout = 0.7

    def __init__(self, **kwargs):
        if 'password' in kwargs:
            self.password = password_prapare(kwargs.pop('password'))
        if 'admin_password' in kwargs:
            self.admin_password = password_prapare(kwargs.pop('admin_password'))
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.clear_vars()

    def clear_vars(self):
        self._command = None
        self._params = None
        self._quick = False
        self._request = None
        self._response = None

    @property
    def is_connected(self):
        return bool(self._conn)

    @property
    def conn(self):
        if hasattr(self, '_conn') and self._conn is not None:
            return self._conn
        self.connect()
        return self._conn

    def connect(self):
        try:
            self._conn = serial.Serial(
                self.port, self.bod,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                writeTimeout=self.writeTimeout
            )
        except serial.SerialException:
            raise ConnectionError(f'Невозможно соединиться с ККМ (порт={self.port})')
        return self.check_port()

    def disconnect(self):
        if self.conn:
            self._conn.close()
            self._conn = None
        return True

    def check_port(self):
        if not self.conn.isOpen():
            raise ConnectionError('Последовательный порт закрыт')
        return True

    def wait_connection(self):
        for i in range(10):
            if self.conn.isOpen():
                return True
            time.sleep(MIN_TIMEOUT * 2)
        raise ConnectionError('Последовательный порт закрыт')

    def _read(self, read=None):
        return self.conn.read(read)

    def _write(self, write):
        return self.conn.write(write)

    def _flush(self):
        return self.conn.flush()

    def ask(self, command, params=None, without_password=False, quick=False, **kwargs):
        self.wait_connection()
        self.clear_vars()
        self._quick = quick
        self.send_ENQ(previous=True)

        if params is None and not without_password:
            params = self.password

        if isinstance(command, int):
            command = bytes([command])

        self.create_request(command, params)

        for i in range(MAX_ATTEMPT):
            self.send_ENQ()
            r = self._response
            if r['error'] and r['error'] == 0x50:
                time.sleep(MIN_TIMEOUT * 10)
                continue
            if r['error']:
                raise KktError(r['error'])
            break
        if not self._quick:
            self.disconnect()
        return r['data'], r['error'], r['command']

    def send_ENQ(self, stx_loop=0, previous=False):
        self._write(ENQ)
        answer = self._read(1)
        if not answer:
            time.sleep(MIN_TIMEOUT)
            answer = self._read(1)
        if answer == NAK:
            if previous:
                return
            return self.send_request()
        elif answer == ACK:
            return self.wait_STX(stx_loop=stx_loop, previous=previous)
        elif not answer:
            self._command = None
            raise ConnectionError('Нет связи с устройством')
        logger.debug('Ожидание конца передачи от KKT')
        time.sleep(MIN_TIMEOUT * 2)
        return self.send_ENQ(previous=previous)

    def create_request(self, command, params):
        self._command = command
        self._params = params
        self._response = None
        data = command
        if params is not None:
            data += force_bytes(params)
        length = len(data)
        content = bytes([length]) + data
        control_summ = get_control_summ(content)
        self._request = STX + content + control_summ
        return self._request

    def send_request(self):
        for i in range(MAX_ATTEMPT):
            self._write(self._request)
            self._flush()
            answer = self._read(1)
            if not answer:
                time.sleep(MIN_TIMEOUT * 2)
                answer = self._read(1)
                if not answer:
                    return self.send_ENQ()
            if answer == ACK:
                return self.wait_STX()
        return self.send_ENQ()

    def read_response(self, previous=False):
        length = ord(self._read(1))
        time.sleep(MIN_TIMEOUT)

        response = self._read(length)
        response_length = len(response)
        time.sleep(MIN_TIMEOUT)

        response_control = self._read(1)

        if previous:
            self._write(ACK)
            self._flush()
            time.sleep(MIN_TIMEOUT * 2)
            return

        if response_length != length:
            logger.info(f'Длина ответа ({length}) не равна длине полученных данных ({response_length})')
            self._write(NAK)
            self._flush()
            return self.send_request()

        command_length = len(self._command)
        response_command = response[:command_length]
        assert self._command == response_command, f'{repr(self._command)} != {repr(response_command)}'

        error = response[command_length:command_length + 1]
        data = response[command_length + 1:]

        control_summ = get_control_summ(
            bytes([response_length]) + response_command + error + data
        )
        if response_control != control_summ:
            logger.info(
                f'Контрольная сумма ({ord(control_summ)}) должна быть равна ({ord(response_control)})'
            )
            self._write(NAK)
            self._flush()
            return self.send_request()

        self._write(ACK)
        if not self._quick:
            self._flush()
            time.sleep(MIN_TIMEOUT * 2)
        self._response = {
            'command': response_command,
            'error': ord(error),
            'data': data
        }
        return self._response

    def wait_STX(self, stx_loop=0, previous=False):
        answer = self._read(1)
        if not answer:
            time.sleep(MIN_TIMEOUT * 2)
            answer = self._read(1)
        if not answer:
            raise RuntimeError('Таймаут STX истек')
        if answer != STX:
            if stx_loop < 10:
                stx_loop += 1
                return self.send_ENQ(stx_loop=stx_loop, previous=previous)
            raise ConnectionError('Нет связи')
        return self.read_response(previous=previous)

class KKT(BaseKKT):
    """ Класс с командами, исполняемыми согласно протокола """

    def x40(self):
        """ Суточный отчет без гашения
            Команда: 40H. Длина сообщения: 5 байт.
                Пароль администратора или системного администратора (4 байта)
            Ответ: 40H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 29, 30
        """
        command = 0x40

        params = self.admin_password
        data, error, command = self.ask(command, params)
        operator = data[0]
        return operator

    def x41(self):
        """ Суточный отчет с гашением
            Команда: 41H. Длина сообщения: 5 байт.
                Пароль администратора или системного администратора (4 байта)
            Ответ: 41H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 29, 30
        """
        command = 0x41

        params = self.admin_password
        data, error, command = self.ask(command, params)
        operator = data[0]
        return operator

    def _x8count(self, command, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        command = command
        count = count2integer(count)
        price = money2integer(price)

        if count < 0 or count > 9999999999:
            raise KktError("Количество должно быть в диапазоне между 0 и 9999999999")
        if price < 0 or price > 9999999999:
            raise KktError("Цена должна быть в диапазоне между 0 и 9999999999")
        if department not in range(17):
            raise KktError("Номер отдела должен быть в диапазоне между 0 и 16")

        if len(text) > 40:
            raise KktError("Текст должнен быть менее или равен 40 символам")
        if len(taxes) != 4:
            raise KktError("Количество налогов должно равняться 4")
        if not isinstance(taxes, (list, tuple)):
            raise KktError("Перечень налогов должен быть типом list или tuple")
        for t in taxes:
            if t not in range(0, 5):
                raise KktError("Налоги должны быть равны 0, 1, 2, 3 или 4")

        count = int5.pack(count)
        price = int5.pack(price)
        department = bytes([department])
        taxes = digits2string(taxes)
        text = text.encode(CODE_PAGE).ljust(40, bytes([0x0]))

        params = self.password + count + price + department + taxes + text
        data, error, command = self.ask(command, params, quick=True)
        operator = data[0]
        return operator


    def x80(self, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        """ Продажа
            Команда: 80H. Длина сообщения: 60 байт.
                Пароль оператора (4 байта)
                Количество (5 байт) 0000000000...9999999999
                Цена (5 байт) 0000000000...9999999999
                Номер отдела (1 байт) 0...16
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 80H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x80
        return self._x8count(
            command=command, count=count, price=price, text=text,
            department=department, taxes=taxes)

    def x81(self, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        """ Покупка
            Команда: 81H. Длина сообщения: 60 байт.
                Пароль оператора (4 байта)
                Количество (5 байт) 0000000000...9999999999
                Цена (5 байт) 0000000000...9999999999
                Номер отдела (1 байт) 0...16
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 81H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x81
        return self._x8count(
            command=command, count=count, price=price, text=text,
            department=department, taxes=taxes)

    def x82(self, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        """ Возврат продажи
            Команда: 82H. Длина сообщения: 60 байт.
                Пароль оператора (4 байта)
                Количество (5 байт) 0000000000...9999999999
                Цена (5 байт) 0000000000...9999999999
                Номер отдела (1 байт) 0...16
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 82H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x82
        return self._x8count(
            command=command, count=count, price=price, text=text,
            department=department, taxes=taxes)

    def x83(self, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        """ Возврат покупки
            Команда: 83H. Длина сообщения: 60 байт.
                Пароль оператора (4 байта)
                Количество (5 байт) 0000000000...9999999999
                Цена (5 байт) 0000000000...9999999999
                Номер отдела (1 байт) 0...16
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 83H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x83
        return self._x8count(
            command=command, count=count, price=price, text=text,
            department=department, taxes=taxes)

    def x84(self, count, price, text='', department=0, taxes=[0, 0, 0, 0]):
        """ Сторно
            Команда: 84H. Длина сообщения: 60 байт.
                Пароль оператора (4 байта)
                Количество (5 байт) 0000000000...9999999999
                Цена (5 байт) 0000000000...9999999999
                Номер отдела (1 байт) 0...16
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 84H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x84
        return self._x8count(
            command=command, count=count, price=price, text=text,
            department=department, taxes=taxes)

    def x85(self, cash=0, summs=[0, 0, 0, 0], discount=0, taxes=[0, 0, 0, 0], text=''):
        command = 0x85

        summa1 = money2integer(summs[0] or cash)
        summa2 = money2integer(summs[1])
        summa3 = money2integer(summs[2])
        summa4 = money2integer(summs[3])
        discount = money2integer(discount)

        for i, s in enumerate([summa1, summa2, summa3, summa4]):
            if s < 0 or s > 9999999999:
                raise KktError(
                    f"Переменная `summa{i+1}` должна быть в диапазоне между 0 и 9999999999")
        if discount < -9999 or discount > 9999:
            raise KktError("Скидка должна быть в диапазоне между -9999 и 9999")

        if len(text) > 40:
            raise KktError("Текст должнен быть менее или равен 40 символам")
        if len(taxes) != 4:
            raise KktError("Количество налогов должно равняться 4")
        if not isinstance(taxes, (list, tuple)):
            raise KktError("Перечень налогов должен быть типом list или tuple")
        for t in taxes:
            if t not in range(0, 5):
                raise KktError("Налоги должны быть равны 0, 1, 2, 3 или 4")

        summa1 = int5.pack(summa1)
        summa2 = int5.pack(summa2)
        summa3 = int5.pack(summa3)
        summa4 = int5.pack(summa4)
        discount = int2.pack(discount)
        taxes = digits2string(taxes)
        text = text.encode(CODE_PAGE).ljust(40, bytes([0x0]))

        params = (self.password + summa1 + summa2 + summa3 + summa4 +
                  discount + taxes + text)
        data, error, command = self.ask(command, params)
        operator = data[0]
        odd = int5.unpack(data[1:6])
        result = {
            'operator': operator,
            'odd': integer2money(odd),
        }
        return result

    def _x8summa(self, command, summa, text='', taxes=[0, 0, 0, 0]):
        """ Общий метод для скидок,
            Команда: 86H. Длина сообщения: 54 байт.
                Пароль оператора (4 байта)
                Сумма (5 байт) 0000000000...9999999999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 86H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = command

        summa = money2integer(summa)

        if summa < 0 or summa > 9999999999:
            raise KktError(
                "Сумма должна быть в диапазоне между 0 и 9999999999")
        if len(text) > 40:
            raise KktError("Текст должнен быть менее или равен 40 символам")
        if len(taxes) != 4:
            raise KktError("Количество налогов должно равняться 4")
        if not isinstance(taxes, (list, tuple)):
            raise KktError("Перечень налогов должен быть типом list или tuple")
        for t in taxes:
            if t not in range(0, 5):
                raise KktError("Налоги должны быть равны 0, 1, 2, 3 или 4")

        summa = int5.pack(summa)
        taxes = digits2string(taxes)
        text = text.encode(CODE_PAGE).ljust(40, chr(0x0))

        params = self.password + summa + taxes + text
        data, error, command = self.ask(command, params, quick=True)
        operator = data[0]
        return operator

    def x86(self, summa, text='', taxes=[0, 0, 0, 0]):
        """ Скидка
            Команда: 86H. Длина сообщения: 54 байт.
                Пароль оператора (4 байта)
                Сумма (5 байт) 0000000000...9999999999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 86H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x86
        return self._x8summa(command=command, summa=summa, text=text,
                             taxes=taxes)

    def x87(self, summa, text='', taxes=[0, 0, 0, 0]):
        """ Надбавка
            Команда: 87H. Длина сообщения: 54 байт.
                Пароль оператора (4 байта)
                Сумма (5 байт) 0000000000...9999999999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 87H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x87
        return self._x8summa(command=command, summa=summa, text=text,
                             taxes=taxes)

    def x88(self):
        """ Аннулирование чека
            Команда: 88H. Длина сообщения: 5 байт.
                Пароль оператора (4 байта)
            Ответ: 88H. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30

        """
        command = 0x88
        data, error, command = self.ask(command)
        operator = data[0]
        return operator

    def x89(self):
        """ Подытог чека
            Команда: 89H. Длина сообщения: 5 байт.
                Пароль оператора (4 байта)
            Ответ: 89H. Длина сообщения: 8 байт.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
                Подытог чека (5 байт) 0000000000...9999999999
        """
        command = 0x89
        data, error, command = self.ask(command)
        operator = data[0]
        return operator

    def x8A(self, summa, text='', taxes=[0, 0, 0, 0]):
        """ Сторно скидки
            Команда: 8AH. Длина сообщения: 54 байта.
                Пароль оператора (4 байта)
                Сумма (5 байт) 0000000000...9999999999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 8AH. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x8A
        return self._x8summa(command=command, summa=summa, text=text,
                             taxes=taxes)

    def x8B(self, summa, text='', taxes=[0, 0, 0, 0]):
        """ Сторно надбавки
            Команда: 8BH. Длина сообщения: 54 байта.
                Пароль оператора (4 байта)
                Сумма (5 байт) 0000000000...9999999999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 8BH. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x8B
        return self._x8summa(command=command, summa=summa,
                             text=text, taxes=taxes)

    def x8C(self):
        """ Повтор документа
            Команда: 8CH. Длина сообщения: 5 байт.
                Пароль оператора (4 байта)
            Ответ: 8CH. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30

            Примечание:
                Команда выводит на печать копию последнего закрытого
                документа продажи, покупки, возврата продажи и
                возврата покупки.
        """
        command = 0x8C
        data, error, command = self.ask(command)
        operator = data[0]
        return operator

    def x8D(self, document_type):
        """ Открыть чек
            Команда: 8DH. Длина сообщения: 6 байт.
                Пароль оператора (4 байта)
                Тип документа (1 байт):
                    0 – продажа;
                    1 – покупка;
                    2 – возврат продажи;
                    3 – возврат покупки
            Ответ: 8DH. Длина сообщения: 3 байта.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
        """
        command = 0x8D

        if document_type not in range(4):
            raise KktError("Тип документа должен быть значением 0, 1, 2 или 3")

        params = self.password + chr(document_type)
        data, error, command = self.ask(command, params)
        operator = data[0]
        return operator

    def x8E(self, payments, taxes, text='', discount_percent=0):
        """ Закрытие чека расширенное
            Команда: 8EH. Длина сообщения: 71+12*5=131 байт.
                Пароль оператора (4 байта)
                Сумма наличных (5 байт) 0000000000...9999999999
                Сумма типа оплаты 2 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 3 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 4 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 5 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 6 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 7 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 8 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 9 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 10 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 11 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 12 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 13 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 14 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 15 (5 байт) 0000000000...9999999999
                Сумма типа оплаты 16 (5 байт) 0000000000...9999999999
                Скидка/Надбавка(в случае отрицательного значения) в % на чек
                    от 0 до 99,99 % (2 байта со знаком) -9999...9999
                Налог 1 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 2 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 3 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Налог 4 (1 байт) «0» – нет, «1»...«4» – налоговая группа
                Текст (40 байт)
            Ответ: 8EH. Длина сообщения: 8 байт.
                Код ошибки (1 байт)
                Порядковый номер оператора (1 байт) 1...30
                Сдача (5 байт) 0000000000...9999999999
        """
        command = 0x8E
        params = self.password
        assert len(payments) == 16, \
            'Количество типов оплат должно быть равно 16.'
        for val in payments:
            params += int5.pack(money2integer(val))
        params += int2.pack(discount_percent)
        assert len(taxes) == 4, 'Количество налогов должно быть равно 4.'
        for val in taxes:
            params += chr(val)
        params += text.encode(CODE_PAGE).ljust(40, chr(0x0))
        data, error, command = self.ask(command, params)
        # operator = ord(data[0])
        return integer2money(int5.unpack(data[1:]))

    
    def xE0(self):
        """ Открыть смену
            Команда: E0H. Длина сообщения: 5байт.
                Пароль оператора (4 байта)
            Ответ: E0H. Длина сообщения: 2 байта.
                Порядковый номер оператора (1 байт) 1...30

            Примечание:
                Команда открывает смену в ФП и переводит ККТ в режим
                «Открытой смены».
        """
        command = 0xE0
        data, error, command = self.ask(command)
        operator = data[0]
        return operator

    def xFC(self):
        """ Получить тип устройства
            Команда: FCH. Длина сообщения: 1 байт.
            Ответ: FCH. Длина сообщения: (8+X) байт.
                Код ошибки (1 байт)
                Тип устройства (1 байт) 0...255
                Подтип устройства (1 байт) 0...255
                Версия протокола для данного устройства (1 байт) 0...255
                Подверсия протокола для данного устройства (1 байт) 0...255
                Модель устройства (1 байт) 0...255
                Язык устройства (1 байт):
                    «0» – русский;
                    «1» – английский;
                    «2» – эстонский;
                    «3» – казахский;
                    «4» – белорусский;
                    «5» – армянский;
                    «6» – грузинский;
                    «7» – украинский;
                    «8» – киргизский;
                    «9» – туркменский;
                    «10» – молдавский;
                Название устройства – строка символов в кодировке WIN1251.
                Количество байт, отводимое под название устройства,
                определяется в каждом конкретном случае
                самостоятельно разработчиками устройства (X байт)

            Примечание:
                Команда предназначена для идентификации устройств.
        """
        command = 0xFC

        data, error, command = self.ask(command, without_password=True)
        result = {
            'device_type': data[0],
            'device_subtype': data[1],
            'protocol_version': data[2],
            'protocol_subversion': data[3],
            'device_model': data[4],
            'device_language': data[5],
            'device_name': data[6:].decode(CODE_PAGE),
        }
        return result