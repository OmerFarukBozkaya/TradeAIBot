import numpy as np
import pandas as pd
import os
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
from Araclar import Araclar
import matplotlib.pyplot as plt
from Indikator import Indikator
from Stratejiler import Stratejiler

from sklearn.preprocessing import StandardScaler, LabelEncoder
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import GRU, Dense, Dropout, Conv1D, MaxPooling1D, Flatten, BatchNormalization
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import ReduceLROnPlateau, EarlyStopping
from sklearn.utils.class_weight import compute_class_weight
from tensorflow.keras.models import load_model
import joblib

# Ayarı değiştir
pd.set_option('display.max_columns', None)

"""
def create_dataset():
    # 1. Veri yükleme optimizasyonu
    data = pd.read_csv('Data/btcusd_1-min_data.csv', usecols=[
        'Timestamp', 'Open', 'Close', 'High', 'Low'
    ])
    # 2. Doğrudan DataFrame üzerinde işlemler
    data['fark'] = data['Close'] - data['Open']

    # 3. Vektörel operasyonlar için numpy kullanımı
    close_np = data['Close'].values
    high_np = data['High'].values
    low_np = data['Low'].values

    # 4. Indikatör hesaplamaları optimizasyonu
    print("Indikatorler hesaplaniyor...")

    bb = Indikator.BB(close_np)
    macd = Indikator.MACD(close_np)

    indicators = {
        'rsi': Indikator.RSI(close_np),
        'ema21': Indikator.EMA(close_np, 21),
        'ema7': Indikator.EMA(close_np, 7),
        'atr': Indikator.ATR(high_np, low_np, close_np),
        'adx': Indikator.ADX(high_np, low_np, close_np),
        'sma50': Indikator.SMA(close_np, 50),
        'sma200': Indikator.SMA(close_np, 200),
        'macd_val': macd[0],
        'macd_signal': macd[1],
        'bb_bot': bb[0],
        'bb_mid': bb[1],
        'bb_top': bb[2],
        'tso_val': Indikator.TSO(high_np, low_np, close_np)
    }
    # 5. Strateji hesaplamaları optimizasyonu
    print("Strategyler hesaplaniyor...")

    strategies = {
        'macd': Stratejiler.MACD(high_np, low_np, close_np),
        'vmzi': Stratejiler.VMZI(high_np, low_np, close_np),
        'vama': Stratejiler.VAMA(high_np, low_np, close_np),
        'tso': Stratejiler.TSO(high_np, low_np, close_np),
        'bb_rsi': Stratejiler.BB_RSI(high_np, low_np, close_np),
        'fdi': Stratejiler.FDI(high_np, low_np, close_np),
        'bb_close': Stratejiler.BB_Close(high_np, low_np, close_np),
        'ma_cross': Stratejiler.MA_Cross(high_np, low_np, close_np),
        'dmo': Stratejiler.DMO(high_np, low_np, close_np),
        'bb_adx': Stratejiler.BB_ADX(high_np, low_np, close_np),
        'ema_stochastic': Stratejiler.EMA_StochasticRSI(high_np, low_np, close_np),
        'cci_atr': Stratejiler.CCI_ATR(high_np, low_np, close_np),
        'signal_moving_avarage': Stratejiler.SignalMovingAvarage(high_np, low_np, close_np),
        'super_trend': Stratejiler.Super_Trend(high_np, low_np, close_np),
        'squeeze_momentum': Stratejiler.SqueezeMomentum(high_np, low_np, close_np),
        'bbtrend_macddema': Stratejiler.BBTrend_MACDDEMA(high_np, low_np, close_np)

    }

    # 6. DataFrame oluşturma optimizasyonu
    last_data = pd.DataFrame({
        'timestamp': data['Timestamp'],
        'open': data['Open'],
        'close': data['Close'],
        'high': data['High'],
        'low': data['Low'],
        'fark': data['fark'],
        **indicators,
        **strategies
    })

    # Ön işleme
    print("On isleme")

    last_data = last_data.dropna()
    last_data.replace({'BUY': 1, 'SELL': -1, False: 0}, inplace=True)

    # Save
    print("Kaydet")
    path = 'Data/btcusd_1-min_data_indicators_strategys.csv'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    last_data.to_csv(path, index=False)
"""

# Özellik ve hedef bölümü
""" 
<Sütun İsimleri>
    'timestamp','open','close','high','low','fark','rsi','ema21','ema7','atr','adx','sma50',
    'sma200','macd_val','macd_signal','bb_bot','bb_mid','bb_top','tso_val','macd','vmzi','vama',
    'tso','bb_rsi','fdi','bb_close','ma_cross','dmo','bb_adx','ema_stochastic','cci_atr','signal_moving_avarage',
    'super_trend','squeeze_momentum','bbtrend_macddema','local_min_max'
</Sütun İsimleri>
"""
def create_model():
    # Veri yükleme
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-5000:, :]  # Son 2000 veriyi al
    data = data.astype(np.float32)

    # Kullanılacak özellikler ve hedef değişken
    # drop_columns = ['timestamp', 'open', 'close', 'high', 'low', 'fark']
    drop_columns = ['timestamp', 'open', 'close', 'high', 'low', 'fark', 'rsi', 'ema21', 'ema7', 'sma50', 'sma200',
                    'macd_val', 'macd_signal', 'bb_bot', 'bb_mid', 'bb_top', 'tso_val']
    x = data.drop(drop_columns, axis=1)
    y = data['local_min_max']
    y.replace({1: 'BUY', -1: 'SELL', 0: 'False'}, inplace=True)

    # Hedef değişkeni encode et
    le = LabelEncoder()
    y = le.fit_transform(y)  # BUY -> 0, SELL -> 1, False -> 2

    # Normalizasyon
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(x)

    # Class weight hesaplama
    class_weights = compute_class_weight('balanced', classes=np.unique(y), y=y)
    class_weight_dict = {i: class_weights[i] for i in range(len(class_weights))}

    # Zaman serisi penceresi (60 zaman adımı geriye bak)
    timestep = 120
    X_sequences = []
    y_sequences = []

    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y[i])

    X_sequences, y_sequences = np.array(X_sequences), np.array(y_sequences)

    # Veri setini bölme (%80 eğitim, %20 test)
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    # Model
    model = Sequential([
        Conv1D(filters=128, kernel_size=3, activation='relu', input_shape=(timestep, X_train.shape[2])),
        BatchNormalization(),
        MaxPooling1D(pool_size=2),
        GRU(128, return_sequences=True),
        Dropout(0.2),
        GRU(64, return_sequences=True),
        Dropout(0.2),
        GRU(32, return_sequences=False),
        Dropout(0.2),
        Dense(64, activation='relu'),
        Dense(32, activation='relu'),
        Dense(3, activation='softmax')  # 3 sınıf (BUY, SELL, False)
    ])

    # Modeli derleme
    optimizer = Adam(learning_rate=0.001)
    model.compile(loss='sparse_categorical_crossentropy', optimizer=optimizer, metrics=['accuracy'])

    # Modeli eğitme
    history = model.fit(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2,
                        class_weight=class_weight_dict)

    # Modelin test doğruluğunu kontrol etme
    test_loss, test_accuracy = model.evaluate(X_test, y_test)
    print(f'Test Accuracy: {test_accuracy:.4f}')

    # Modelin kayit edilmesi
    model.save('tradeai_model.keras')
    joblib.dump(scaler, 'scaler.pkl')

def test_model():
    # Modelin yüklenmesi
    scaler = joblib.load('scaler.pkl')
    model = load_model('tradeai_model.keras')

    # Veri yükleme
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[:5000, :]  # Son 2000 veriyi al
    data = data.astype(np.float32)

    # Kullanılacak özellikler ve hedef değişken
    # drop_columns = ['timestamp', 'open', 'close', 'high', 'low', 'fark']
    drop_columns = ['timestamp', 'open', 'close', 'high', 'low', 'fark', 'rsi', 'ema21', 'ema7', 'sma50', 'sma200',
                    'macd_val', 'macd_signal', 'bb_bot', 'bb_mid', 'bb_top', 'tso_val']
    x = data.drop(drop_columns, axis=1)
    y = data['local_min_max']
    y.replace({1: 'BUY', -1: 'SELL', 0: 'False'}, inplace=True)

    # Hedef değişkeni encode et
    le = LabelEncoder()
    y = le.fit_transform(y)  # BUY -> 0, SELL -> 1, False -> 2

    # Normalizasyon
    X_scaled = scaler.fit_transform(x)

    # Class weight hesaplama
    class_weights = compute_class_weight('balanced', classes=np.unique(y), y=y)
    class_weight_dict = {i: class_weights[i] for i in range(len(class_weights))}

    # Zaman serisi penceresi (60 zaman adımı geriye bak)
    timestep = 120
    X_sequences = []
    y_sequences = []

    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y[i])

    X_sequences, y_sequences = np.array(X_sequences), np.array(y_sequences)

    # Veri setini bölme (%80 eğitim, %20 test)
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    # Modelin test doğruluğunu kontrol etme
    test_loss, test_accuracy = model.evaluate(X_test, y_test)
    print(f'Test Accuracy: {test_accuracy:.4f}')

def predict_single_row(input_df):
    # Model ve scaler'ı yükle
    scaler = joblib.load('scaler.pkl')
    model = load_model('tradeai_model.keras')

    # Kullanılacak sütunlar (önceden çıkarılanları tekrar ekleme!)
    drop_columns = ['timestamp', 'open', 'close', 'high', 'low', 'fark', 'rsi', 'ema21', 'ema7', 'sma50', 'sma200',
                    'macd_val', 'macd_signal', 'bb_bot', 'bb_mid', 'bb_top', 'tso_val']

    input_df = input_df.drop(drop_columns,axis=1)
    # Normalizasyon
    input_scaled = scaler.transform(input_df)

    # Modelin beklediği şekle getirme (120 zaman adımı gerekiyor)
    timestep = 120
    input_sequence = np.tile(input_scaled, (timestep, 1))  # 120 zaman adımı olacak şekilde kopyala
    input_sequence = np.expand_dims(input_sequence, axis=0)  # Model için (1, 120, feature_sayısı) şekline getir

    # Tahmin yap
    prediction = model.predict(input_sequence)
    predicted_class = np.argmax(prediction)

    # Etiketleri geri çevir
    label_map = {0: 'BUY', 1: 'SELL', 2: 'False'}
    return label_map[predicted_class]

#create_model()
#test_model()
"""
# Tahmini al
data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
data = data.iloc[-55:, :]  # Son 2000 veriyi al
data = data.astype(np.float32)
sample_input=data
prediction_result = predict_single_row(sample_input)
print("Tahmin Sonucu:", prediction_result)
"""