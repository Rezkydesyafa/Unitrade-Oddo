import math

# Definisi metode pengiriman yang didukung UniTrade (tahap prototype).
SHIPPING_METHODS = {
    'pickup': {
        'label': 'Ambil Sendiri / COD',
        'description': 'Transaksi tatap muka, tanpa ongkir.',
        'logo': '/unitrade_theme/static/src/img/shipping/pickup.svg',
        'sequence': 10,
        'requires_gps': False,
    },
    'gosend': {
        'label': 'GoSend Instant',
        'description': 'Diantar kurir instan, ongkir sesuai jarak.',
        'logo': '/unitrade_theme/static/src/img/shipping/gosend-gojek-icon.png',
        'sequence': 20,
        'requires_gps': True,
    },
}

DEFAULT_SHIPPING_METHOD = 'pickup'

# Tabel rate hardcode GoSend untuk area DIY (tanpa API eksternal).
# Format: (batas_atas_km_inklusif, ongkir). None = tak terbatas (tier terakhir).
GOSEND_RATE_TABLE = [
    (3, 12000),
    (8, 18000),
    (15, 25000),
    (25, 35000),
    (None, 45000),
]

# Radius bumi rata-rata dalam kilometer untuk rumus Haversine.
_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lng1, lat2, lng2):
    """Hitung jarak (km) antara dua titik GPS dengan rumus Haversine.

    Hasil dibulatkan ke 2 desimal agar penentuan tier ongkir deterministik.
    """
    lat1 = float(lat1)
    lng1 = float(lng1)
    lat2 = float(lat2)
    lng2 = float(lng2)

    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(_EARTH_RADIUS_KM * c, 2)


def gosend_rate_for_distance(distance_km):
    """Kembalikan ongkir (int) sesuai GOSEND_RATE_TABLE untuk jarak tertentu.

    Tier inklusif batas atas: distance_km <= batas -> ongkir tier tersebut.
    Jarak negatif diperlakukan sebagai 0.
    """
    distance_km = max(float(distance_km or 0.0), 0.0)
    for upper_bound, cost in GOSEND_RATE_TABLE:
        if upper_bound is None or distance_km <= upper_bound:
            return int(cost)
    # Fallback defensif (seharusnya tidak tercapai karena tier terakhir None).
    return int(GOSEND_RATE_TABLE[-1][1])


def is_valid_coordinate(lat, lng):
    """True bila lat/lng numerik, tidak kosong, tidak 0, dan dalam rentang valid.

    Latitude valid -90..90, longitude valid -180..180. Nilai kosong atau 0
    dianggap tidak valid karena merupakan default field koordinat UniTrade.
    """
    if lat in (None, '', False) or lng in (None, '', False):
        return False
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False
    if lat == 0.0 or lng == 0.0:
        return False
    if not (-90.0 <= lat <= 90.0):
        return False
    if not (-180.0 <= lng <= 180.0):
        return False
    return True
