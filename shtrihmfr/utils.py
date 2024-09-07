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

import struct

__all__ = (
    'int2', 'int4', 'int5', 'int6', 'int7', 'int8',
    'money2integer', 'integer2money', 'count2integer',
    'get_control_summ', 'string2bits', 'bits2string',
    'digits2string', 'password_prapare',
    'force_text', 'force_bytes',
)

class Struct(struct.Struct):
    """ Преобразователь """

    def __init__(self, *args, **kwargs):
        self.length = kwargs.pop('length', None)
        super().__init__(*args, **kwargs)

    def unpack(self, value):
        value = self.pre_value(value)
        return super().unpack(value)[0]

    def pack(self, value):
        value = super().pack(value)
        return self.post_value(value)

    def pre_value(self, value):
        """ Обрезает или добавляет нулевые байты """
        if self.size:
            if self.format in (b'h', b'i', b'I', b'l', b'L', b'q', b'Q'):
                _len = len(value)
                if _len < self.size:
                    value = value.ljust(self.size, bytes([0x0]))
                elif _len > self.size:
                    value = value[:self.size]
        return value

    def post_value(self, value):
        """ Обрезает или добавляет нулевые байты """
        if self.length:
            if self.format in (b'h', b'i', b'I', b'l', b'L', b'q', b'Q'):
                _len = len(value)
                if _len < self.length:
                    value = value.ljust(self.length, bytes([0x0]))
                elif _len > self.length:
                    value = value[:self.length]
        return value

# Специальный класс для работы с 5-байтовыми числами
class Int5:
    def pack(self, value):
        # Упаковываем значение в 5 байт
        return value.to_bytes(5, byteorder='little', signed=True)

    def unpack(self, value):
        # Распаковываем 5 байт в число
        return int.from_bytes(value, byteorder='little', signed=True)

# Объекты класса Struct и Int5
int2 = Struct(b'h', length=2)
int3 = Struct(b'i', length=3)
int4 = Struct(b'i', length=4)
int5 = Int5()  # Используем специальный класс для 5 байтов
int6 = Struct(b'q', length=6)
int7 = Struct(b'q', length=7)
int8 = Struct(b'q', length=8)

def string2bits(string):
    """ Convert string to bit array """
    result = []
    for char in string:
        bits = bin(ord(char))[2:]
        bits = '00000000'[len(bits):] + bits
        result.extend([int(b) for b in bits])
    return result

def bits2string(bits):
    """ Convert bit array to string """
    chars = []
    for b in range(len(bits) // 8):
        byte = bits[b * 8:(b + 1) * 8]
        chars.append(bytes([int(''.join([str(bit) for bit in byte]), 2)]))
    return b''.join(chars)

def money2integer(money, digits=2):
    """
    Преобразует decimal или float значения в целое число, согласно
    установленной десятичной кратности.
    Например, money2integer(2.3456, digits=3) вернёт  2346
    """
    return int(round(float(money) * 10**digits))

def integer2money(integer, digits=2):
    """
    Преобразует целое число в значение float, согласно
    установленной десятичной кратности.
    Например, integer2money(2346, digits=3) вернёт  2.346
    """
    return round(float(integer) / 10**digits, digits)

def count2integer(count, coefficient=1, digits=3):
    """
    Преобразует количество согласно заданного коэффициента
    """
    return money2integer(count, digits=digits) * coefficient

def get_control_summ(string):
    """
    Подсчет CRC
    """
    result = 0
    for s in string:
        result ^= s
    return bytes([result])


def digits2string(digits):
    """
    Преобразует список из целых или шестнадцатеричных значений в строку
    """
    return b''.join([bytes([x]) for x in digits])

def password_prapare(password):

    if isinstance(password, (list, tuple)):
        try:
            return digits2string(password[:4])
        except:
            raise TypeError('Тип пароля неидентифицирован')

    password = int(password)

    if password > 9999:
        raise ValueError('Пароль должен быть от 0 до 9999')

    return int4.pack(password)

def force_text(s, encoding='utf-8', errors='strict'):
    "Преобразование объекта в строку Юникода."

    if isinstance(s, str):
        return s

    if isinstance(s, bytes):
        return s.decode(encoding, errors)

    return str(s)

def force_bytes(s, encoding='utf-8', errors='strict'):
    "Преобразование объекта в строку байт-символов."
    if isinstance(s, bytes):
        return s
    if isinstance(s, str):
        return s.encode(encoding, errors)
    return str(s).encode(encoding, errors)
