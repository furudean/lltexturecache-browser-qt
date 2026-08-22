from datetime import datetime

from PySide6.QtCore import QDateTime, QLocale


def format_count(number: int) -> str:
    return QLocale().toString(number)


def format_size(size: int) -> str:
    return QLocale().formattedDataSize(size, 1, QLocale.DataSizeFormat.DataSizeTraditionalFormat)


def format_time(time: datetime) -> str:
    stamp = QDateTime.fromSecsSinceEpoch(int(time.timestamp()))

    return QLocale().toString(stamp, QLocale.FormatType.ShortFormat)
