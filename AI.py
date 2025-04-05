import numpy as np
import pandas as pd
import os
import time
from keras_tuner import RandomSearch

import Araclar
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
import matplotlib.pyplot as plt
import plotly.express as px

import joblib
import seaborn as sns

from keras.src.layers import MultiHeadAttention, LayerNormalization

from sklearn.preprocessing import StandardScaler, LabelEncoder, label_binarize
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import (confusion_matrix, classification_report, precision_score, recall_score, f1_score, roc_curve, auc )
from sklearn.decomposition import PCA

import tensorflow as tf
from tensorflow.keras.models import load_model,Model
from tensorflow.keras.layers import GRU, Dense, Dropout, Conv1D, MaxPooling1D, Flatten, BatchNormalization, Bidirectional, Input, Conv1D, BatchNormalization, MaxPooling1D, Bidirectional, LSTM, Dropout, Dense, Multiply, Permute, Lambda, Flatten, Add, Activation, Concatenate
from tensorflow.keras.optimizers import Adam

# Ayarı değiştir
pd.set_option('display.max_columns', None)

# Global sabitler
""" close & indikator """
#DROP_COLUMNS = ['timestamp', 'open', 'high', 'low','macd','vmzi','tso','bb_rsi','fdi', 'bb_close','ma_cross','dmo','bb_adx','ema_stochastic','cci_atr','signal_moving_avarage','super_trend','squeeze_momentum','bbtrend_macddema','local_min_max']
DROP_COLUMNS = None

features = ['close','adx', 'sma50', 'sma200','ema21','ema7','parabolic_sar','super_trend_val','alpha_trend','bb_trend',
            'sma_diff','signal_moving_avarage_50','bb_bot', 'bb_mid', 'bb_top']
#features = None

""" Tüm colonlar
[
# Fiyat verileri

'timestamp', 'open', 'close', 'high', 'low', 
# İndikatör

## Trend
'adx', 'sma50', 'sma200','ema21','ema7','parabolic_sar','super_trend_val','alpha_trend','bb_trend',
'sma_diff','signal_moving_avarage_50','bb_bot', 'bb_mid', 'bb_top',

## Momentum
'rsi','macd_val', 'macd_signal','macd_dema_macd', 'macd_dema_signal','stochastic_rsi_k', 'stochastic_rsi_d','cci', 'momentum',

## Volatilite
'atr','bb_bot', 'bb_mid', 'bb_top', 'volatility', 

## Ortalama geri dönüş
'fark', 'log_return', 

## Diger
'tso_val',
  
# Strategy
'macd', 'vmzi', 'tso', 'bb_rsi', 'fdi', 'bb_close', 'ma_cross', 'dmo','bb_adx', 'ema_stochastic', 'cci_atr', 
'signal_moving_avarage','super_trend', 'squeeze_momentum', 'bbtrend_macddema',
]

['close','adx', 'sma50', 'sma200','ema21','ema7','parabolic_sar','super_trend_val','alpha_trend','bb_trend',
'sma_diff','signal_moving_avarage_50','bb_bot', 'bb_mid', 'bb_top']
"""
TIMESTEP = 20

# =============================================================================
# Yardımcı Fonksiyonlar
# =============================================================================
def data_frame_info(data):
    """
    Aldığı dataframe hakkında bilgileri listeler.
    :param data: pandas.DataFrame()
    :return:
    """
    print('=' * 40, ' Veri seti hakkında bilgiler ', '=' * 40)

    print('=' * 40, ' Sütun isimleri, kaç tane eksik veri var, veri tipleri vb. ','=' * 40 )
    print(data.info())
    print('=' * 40, ' Her sütundaki eşsiz (unique) değer sayısını ','=' * 40 )
    print(data.nunique())
    print('=' * 40, ' Her sütundaki eksik değerleri ', '=' * 40)
    print(data.isnull().sum())
    print('=' * 40, ' Her sütunun veri tipini ','=' * 40)
    print(data.dtypes)
    print('=' * 40, ' Local_Min_Max frekans ', '=' * 40)
    print(data['local_min_max'].value_counts().sort_index())

    if input('Rapor oluşturulsun mu : (1: Evet, Diğer: Hayır)')=='1':
        from ydata_profiling import ProfileReport
        profile = ProfileReport(data, explorative=True)
        profile.to_file("Data/data_frame_rapor.html")

def load_data(file_path='Data/btcusd_1-min_data_indicators_strategys.csv', nrows=None,mrows=None):
    """
    Belirtilen CSV dosyasını yükler ve istenirse son n satırı alır.
    :param file_path: string : CSV dosyasının konumu.
    :param nrows: int : Sondan başlanacak şekilde kaç satır alınacak.
    :return: pandas.DataFrame() : Okunan dosya her colonun veri tipi np.float32'ye dönüştürülerek dataframe şeklinde geri döndürülür.
    """
    data = pd.read_csv(file_path)
    if nrows and mrows is None:
        data = data.iloc[-nrows:, :]
    elif mrows and nrows:
        data = data.iloc[-nrows:-mrows,:]
    return data

def preprocess_data(data, drop_columns=DROP_COLUMNS,features=features, target_col='local_min_max',le=None,scaler=None):
    """
    Veriyi özellikler (X) ve hedef (y) olarak ayırır; hedefi encode eder ve özellikleri normalize eder.
    :param data: pandas.DataFrame() : İşlenecek dataframe.
    :param drop_columns: list : Dataframe'den çıkarılacak colonlar.
    :param target_col: string : Tahmin edilecek colon adı.
    :return: pandas.core.frame.DataFrame , numpy.ndarray, numpy.ndarray, scaler, le : Özellik dataframesi , Ölçeklenmiş özellik numpy.ndarray , Encode edilmiş hedef numpy.ndarray , scaler nesnesi , encode nesnesi
    """
    if drop_columns is not None:
        print('X drop edildi')
        X = data.drop(drop_columns, axis=1)
    elif features is not None:
        print('X seçildi')
        X = data[features]
    else:
        print('Hiçbir colon seçilmedi !!!')
        X = data['close','rsi']

    y = data[target_col].copy()
    y_decoded = y.replace({1: 'BUY', -1: 'SELL', 0: 'False'})

    # Hedef etiketleri encode et
    if le is None:
        le = LabelEncoder()
        y_encoded = le.fit_transform(y_decoded)
    else:
        y_encoded = le.transform(y_decoded)


    # Özellikleri normalize et
    if scaler is None:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    else:
        X_scaled = scaler.transform(X)


    return X, X_scaled,y, y_encoded, scaler, le

def create_sequences(X_scaled, y, timestep=TIMESTEP):
    """
    Zaman serisi verilerini pencerelemeye yarayan fonksiyon.
    :param X_scaled: numpy.ndarray : Özellik arrayi
    :param y: numpy.ndarray : Hedef arrayi
    :param timestep: int : Pencere uzunluğu
    :return: np.array , np.array : Pencereler haline getirilmiş özellik np.array'i , Pencereler haline getirilmiş hedef np.array'i
    """
    X_sequences, y_sequences = [], []
    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y[i])
    return np.array(X_sequences), np.array(y_sequences)

def plot_heatmap(data, title="Özellik Korelasyon Matrisi"):
    """
    Korelasyon matrisini hesaplar ve görselleştirir.
    :param data: pandas.DataFrame : Korelasyon matrisi hesaplanacak data.
    :param title: string : Grafik başlığı
    :return:
    """
    plt.figure(figsize=(12, 10))
    sns.heatmap(data.corr(), annot=True, fmt='.2f', cmap='coolwarm')
    plt.title(title)
    plt.show()

def perform_pca(X_scaled, original_columns):
    """
    PCA uygulayarak bileşen sayısını belirler ve özellik önem sıralamasını yazdırır.
    :param X_scaled: numpy.ndarray : Ölçeklenmiş özellikler
    :param original_columns: pandas.core.indexes.base.Index : colon isimleri
    :return:
    """
    pca = PCA(n_components=0.98)
    X_pca = pca.fit_transform(X_scaled)
    print("Özellik sayısı (orijinal):", len(original_columns))
    print("Özellik sayısı (PCA sonrası):", X_pca.shape[1])

    loadings = pca.components_.T
    loadings_df = pd.DataFrame(loadings, index=original_columns,
                               columns=[f'PC{i+1}' for i in range(X_pca.shape[1])])
    feature_importance = loadings_df.abs().sum(axis=1)
    feature_importance_sorted = feature_importance.sort_values(ascending=False)
    print(feature_importance_sorted)
    return X_pca.shape[1], feature_importance_sorted

def build_model_random_search(X_train_shape, timestep=TIMESTEP):
    """
    Modelin hiperparametre optimizasyonu için yapılandırılmasını sağlar.
    :param X_train_shape: numpy.ndarray : Eğitim için kullanılacak özellik arrayi.
    :param timestep: int : Pencere uzunluğu
    :return: RandomSearch :
    """
    def build_model(hp):
        inputs = Input(shape=(timestep, X_train_shape[2]))
        # CNN Katmanı
        conv_filters = hp.Choice('conv_filters', values=[64, 128, 256])
        kernel_size = hp.Choice('kernel_size', values=[3, 5, 7])
        x = Conv1D(filters=conv_filters, kernel_size=kernel_size, activation='relu', padding='same')(inputs)
        x = BatchNormalization()(x)
        pool_size = hp.Choice('pool_size', values=[2, 3])
        x = MaxPooling1D(pool_size=pool_size)(x)

        # GRU Katmanları
        gru_units1 = hp.Choice('gru_units1', values=[64, 128, 256])
        x = Bidirectional(GRU(gru_units1, return_sequences=True))(x)
        dropout_rate1 = hp.Float('dropout_rate1', 0.2, 0.5, step=0.1)
        x = Dropout(dropout_rate1)(x)
        gru_units2 = hp.Choice('gru_units2', values=[32, 64, 128])
        x = Bidirectional(GRU(gru_units2, return_sequences=True))(x)

        # Attention Mekanizması
        num_heads = hp.Choice('num_heads', values=[2, 4, 8])
        key_dim = hp.Choice('key_dim', values=[32, 64, 128])
        attention_output = MultiHeadAttention(num_heads=num_heads, key_dim=key_dim)(x, x)
        x = LayerNormalization(epsilon=1e-6)(x + attention_output)

        # Sınıflandırma Katmanları
        x = Flatten()(x)
        dense_units = hp.Choice('dense_units', values=[32, 64, 128])
        x = Dense(dense_units, activation='relu')(x)
        dropout_rate2 = hp.Float('dropout_rate2', 0.2, 0.5, step=0.1)
        x = Dropout(dropout_rate2)(x)
        outputs = Dense(3, activation='softmax')(x)

        learning_rate = hp.Float('learning_rate', 0.0001, 0.01, sampling='log')
        optimizer = Adam(learning_rate=learning_rate)
        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=optimizer, metrics=['accuracy'])
        return model

    tuner = RandomSearch(
        build_model, objective='val_accuracy', max_trials=20, executions_per_trial=1,
        directory='ktuner_dir', project_name='tradeai_model_tuning'
    )
    return tuner

def grafik_ciz_3d(data, x, y, z, target_col_name):
    """
    Aldığı parametreler doğrultusunda veriyi 3d olarak görselleştirir

    :param data: pandas.DataFrame() : Tüm veriyi tutan dataframe
    :param x: string : x ekseni için colon adı
    :param y: string : y ekseni için colon adı
    :param z: string : z ekseni için colon adı
    :param target_col_name: string : Renk olarak sınıflandırılır . Benzersiz her değer için 1 renk atanır ve görselleştirilir.
    :return:
    """
    df = pd.DataFrame({
        x: data[x],
        y: data[y],
        z: data[z],
        'target': data[target_col_name]
    })
    fig = px.scatter_3d(df, x=x, y=y, z=z, color='target')
    fig.show()
# =============================================================================
# Model Oluşturma Fonksiyonları
# =============================================================================
def create_model_best_parametre():
    """
    En iyi hiperparametrelerin belirlenmesi ve modelin eğitilmesi.
    Eğitilen model, kullanıcı tercihine bağlı olarak kaydedilir.
    """
    # Veri yükleme ve ön işleme
    data = load_data(nrows=6000)
    data = data.iloc[-6000:, :]
    X, X_scaled, y_encoded, scaler, le = preprocess_data(data)
    plot_heatmap(X)
    perform_pca(X_scaled, X.columns)

    # Sınıf ağırlıkları hesaplama
    class_weights = compute_class_weight('balanced', classes=np.unique(y_encoded), y=y_encoded)
    class_weight_dict = {i: class_weights[i] for i in range(len(class_weights))}

    # Zaman serisi penceresi oluşturma
    X_sequences, y_sequences = create_sequences(X_scaled, y_encoded)

    # Veri setini bölme
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    # Hiperparametre optimizasyonu ve model eğitimi
    tuner = build_model_random_search(X_train.shape, timestep=TIMESTEP)
    tuner.search(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2, verbose=1)
    best_hps = tuner.get_best_hyperparameters(num_trials=1)[0]

    print("En iyi hiperparametreler:")
    print(f"Conv Filters: {best_hps.get('conv_filters')}")
    print(f"Kernel Size: {best_hps.get('kernel_size')}")
    print(f"GRU Units 1: {best_hps.get('gru_units1')}")
    print(f"GRU Units 2: {best_hps.get('gru_units2')}")
    print(f"Dense Units: {best_hps.get('dense_units')}")
    print(f"Dropout Rate 1: {best_hps.get('dropout_rate1')}")
    print(f"Dropout Rate 2: {best_hps.get('dropout_rate2')}")
    print(f"Learning Rate: {best_hps.get('learning_rate')}")

    # En iyi modelin yeniden eğitilmesi
    model = tuner.hypermodel.build(best_hps)
    history = model.fit(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2)

    # Eğitim geçmişini görselleştirme
    loss_values = history.history["loss"]
    val_loss_values = history.history["val_loss"]
    acc_values = history.history["accuracy"]
    val_acc_values = history.history["val_accuracy"]
    epochs_range = range(1, len(loss_values) + 1)

    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(epochs_range, loss_values, "bo-", label="Eğitim Kaybı")
    plt.plot(epochs_range, val_loss_values, "ro-", label="Doğrulama Kaybı")
    plt.xlabel("Epoch")
    plt.ylabel("Kayıp")
    plt.title("Eğitim ve Doğrulama Kaybı")
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(epochs_range, acc_values, "bo-", label="Eğitim Doğruluğu")
    plt.plot(epochs_range, val_acc_values, "ro-", label="Doğrulama Doğruluğu")
    plt.xlabel("Epoch")
    plt.ylabel("Doğruluk")
    plt.title("Eğitim ve Doğrulama Doğruluğu")
    plt.legend()
    plt.show()

    # Modelin test verisi üzerindeki performansı
    test_loss, test_accuracy = model.evaluate(X_test, y_test)
    print(f'Test Accuracy: {test_accuracy:.4f}')

    if input("Kaydetmek için '1' tuşlayın: ") == "1":
        os.makedirs('Data/Model', exist_ok=True)
        model.save('Data/Model/tradeai_model.keras')
        joblib.dump(scaler, 'Data/Model/scaler.pkl')
        joblib.dump(le, 'Data/Model/label_encoder.pkl')
    else:
        exit(0)

def create_model_best_model():
    """
    Farklı model varyantlarını deneyip, en başarılı olanı seçer ve kaydeder.
    """
    # Veri yükleme ve ön işleme
    data = load_data(nrows=2500000)
    data = data.iloc[-2500000:, :]
    X, X_scaled, y, y_encoded, scaler, le = preprocess_data(data)

    # Veri hakkında bilgiler
    print('1 : Özellik korelasyon matrisi\n2 : Confusion matrisi\n3 : ROC AUC hesaplama')
    matris_hesaplamalar = input('(1,2,3 : Evet, diğer : Hayır) : ')
    if  '1' in matris_hesaplamalar:
        plot_heatmap(pd.concat([X, data['local_min_max']], axis=1), "Özellik Korelasyon Matrisi")
        perform_pca(X_scaled, X.columns)

        # Özellik önem sırası
        from sklearn.feature_selection import mutual_info_classif

        mi_scores = mutual_info_classif(X_scaled, y)
        mi_df = pd.DataFrame({'Özellik': X.columns, 'MI Skor': mi_scores})
        mi_df.sort_values('MI Skor', ascending=False, inplace=True)
        print(mi_df)

        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier()
        model.fit(X_scaled, y)
        importance = model.feature_importances_
        print(importance)

    # Zaman serisi penceresi oluşturma
    X_sequences, y_sequences = create_sequences(X_scaled, y_encoded)
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    # y_train etiketlerinizin dağılımına göre ağırlıkları hesaplayın
    classes = np.unique(y_train)
    class_weights = compute_class_weight('balanced', classes=classes, y=y_train)
    class_weight_dict = {i: weight for i, weight in zip(classes, class_weights)}
    print("Class weights:", class_weight_dict)

    # Model varyantları
    def model_v6():
        inputs = Input(shape=(TIMESTEP, X_train.shape[2]))
        # Pozisyonel embedding: her zaman adımı için trainable bir embedding ekleniyor
        pos_indices = tf.range(start=0, limit=TIMESTEP, delta=1)
        pos_embedding = tf.keras.layers.Embedding(input_dim=TIMESTEP, output_dim=X_train.shape[2])(pos_indices)
        # pos_embedding boyutu: (TIMESTEP, feature_dim) -> bunu tüm örneklere eklemek için broadcast edelim
        x = inputs + pos_embedding

        attn_output = MultiHeadAttention(num_heads=4, key_dim=64)(x, x)
        x = Add()([x, attn_output])
        x = LayerNormalization(epsilon=1e-6)(x)
        x = Flatten()(x)
        x = Dense(128, activation='relu')(x)
        x = Dropout(0.4)(x)
        outputs = Dense(3, activation='softmax')(x)
        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy',
                      optimizer=Adam(learning_rate=0.0001),
                      metrics=['accuracy'])
        return model
    models={
        'model v6':model_v6()
    }

    results = {}
    for name, model in models.items():
        print(f"\n=== {name} Modeli Eğitiliyor ===")
        model.summary()
        bas_fit=time.perf_counter()
        history = model.fit(X_train, y_train, epochs=200, batch_size=64, validation_split=0.2, verbose=1,class_weight=class_weight_dict)
        son_fit=time.perf_counter()
        test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
        results[name] = test_accuracy
        print(f"=============================================\n"
              f"{name} Test Accuracy: {test_accuracy:.4f}\n"
              f"{name} Train time: {Araclar.Araclar.saniye_to_hms(son_fit-bas_fit)}\n"
              f"=============================================")
        # Tahminler ve metrikler
        y_pred = model.predict(X_test)
        y_pred_classes = np.argmax(y_pred, axis=1)
        true_labels = le.inverse_transform(y_test)
        predicted_labels = le.inverse_transform(y_pred_classes)

        cm = confusion_matrix(true_labels, predicted_labels, labels=le.classes_)
        if '2' in matris_hesaplamalar:
            plt.figure(figsize=(8, 6))
            sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                        xticklabels=le.classes_, yticklabels=le.classes_)
            plt.xlabel('Predicted')
            plt.ylabel('Actual')
            plt.title(f"{name} - Confusion Matrix")
            plt.show()

        cr = classification_report(true_labels, predicted_labels, target_names=le.classes_, output_dict=True)
        cr_df = pd.DataFrame(cr).transpose()
        print(f"\n{name} - Classification Report:")
        print(cr_df)

        n_classes = 3
        y_test_bin = label_binarize(y_test, classes=list(range(n_classes)))
        fpr, tpr, roc_auc = {}, {}, {}
        for i in range(n_classes):
            fpr[i], tpr[i], _ = roc_curve(y_test_bin[:, i], y_pred[:, i])
            roc_auc[i] = auc(fpr[i], tpr[i])

        class_names = le.inverse_transform(list(range(n_classes)))
        if '3' in matris_hesaplamalar:
            plt.figure()
            for i in range(n_classes):
                plt.plot(fpr[i], tpr[i], label=f'Class {class_names[i]} (AUC = {roc_auc[i]:0.2f})')
            plt.plot([0, 1], [0, 1], 'k--')
            plt.xlabel('False Positive Rate')
            plt.ylabel('True Positive Rate')
            plt.title(f'ROC Curve - {name}')
            plt.legend(loc="lower right")
            plt.show()

        print(f"\n{name} için Ek Değerlendirme Raporu:")
        print(f"Test Loss: {test_loss:.4f}")
        print(f"Test Accuracy: {test_accuracy:.4f}")

    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    print("\nModeller başarı oranlarına göre sıralandı:")
    for name, acc in sorted_results:
        print(f"{name}: {acc:.4f}")

    best_model_name = sorted_results[0][0]
    print(f"\nEn iyi model: {best_model_name} (Accuracy: {results[best_model_name]:.4f})")
    if input("Modeli kaydetmek ister misiniz? (1: Evet, diğer: Hayır): ") == "1":
        os.makedirs('Data/Model', exist_ok=True)
        models[best_model_name].save('Data/Model/tradeai_model.keras')
        joblib.dump(scaler, 'Data/Model/scaler.pkl')
        joblib.dump(le, 'Data/Model/label_encoder.pkl')
    else:
        print('Kayit edilmedi !!!')

# =============================================================================
# Test ve Tahmin Fonksiyonları
# =============================================================================
def test_model():
    """
    Kaydedilmiş modelin test verileri üzerinde değerlendirilmesi ve metriklerin raporlanması.
    """
    on_ek = input('Model on eki: ')
    scaler = joblib.load(f'Data/Model/{on_ek}scaler.pkl')
    model = load_model(f'Data/Model/{on_ek}tradeai_model.keras')
    le = joblib.load(f'Data/Model/{on_ek}label_encoder.pkl')

    data = load_data(nrows=6000,mrows=1)
    data = data.iloc[:,:]

    X, X_scaled, y, y_encoded, scaler, le = preprocess_data(data,le=le, scaler=scaler)

    X_sequences, y_sequences = create_sequences(X_scaled, y_encoded)
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
    print(f"\n{'=' * 40}")
    print(f"Test Doğruluğu: {test_accuracy:.4f}")
    print(f"Test Kaybı: {test_loss:.4f}")
    print(f"{'=' * 40}\n")

    y_pred = np.argmax(model.predict(X_test), axis=1)
    y_test_labels = le.inverse_transform(y_test)
    y_pred_labels = le.inverse_transform(y_pred)

    print("Sınıflandırma Raporu:")
    print(classification_report(
        y_test_labels,
        y_pred_labels,
        target_names=le.classes_,
        digits=4
    ))

    precision = precision_score(y_test, y_pred, average='weighted')
    recall = recall_score(y_test, y_pred, average='weighted')
    f1 = f1_score(y_test, y_pred, average='weighted')

    print(f"\nWeighted Ortalama Metrikler:")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1 Score: {f1:.4f}")

    df_results = pd.DataFrame({
        "Gerçek Değerler": y_test_labels,
        "Tahmin Edilen Değerler": y_pred_labels,
    })
    df_results["Durum"] = df_results.apply(lambda row: "OK" if row["Gerçek Değerler"] == row["Tahmin Edilen Değerler"] else "XX", axis=1)

    # Tahmin sonucu
    print(model.summary())
    print(df_results)
    df_results.to_csv("Data/test_sonuclari.csv", index=False)

    # Örnek zaman dizisi (Gerçek zaman verin varsa burada kullanabilirsiniz)
    time_series = range(len(y_test_labels))  # Örneğin veri sırası olabilir

    # Renkleri belirleme fonksiyonu
    def get_color(label):
        if label == "BUY":
            return "green"
        elif label == "SELL":
            return "red"
        else:
            return "blue"

    # Renkleri belirleme
    actual_colors = [get_color(label) for label in y_test_labels]
    pred_colors = [get_color(label) for label in y_pred_labels]

    close_prices = X_test[:, -1, 0]

    # --- GERÇEK DEĞERLER GRAFİĞİ ---
    plt.figure(figsize=(12, 5))
    for i in range(len(close_prices) - 1):
        plt.plot(time_series[i:i + 2], close_prices[i:i + 2], color=actual_colors[i])  # Çizgiyi çizer
    plt.scatter(time_series, close_prices, c=actual_colors, label="Gerçek Değerler", alpha=0.7, edgecolors='black')
    plt.title("Gerçek Değerler Grafiği")
    plt.xlabel("Zaman")
    plt.ylabel("Kapanış (Close) Fiyatı")
    plt.legend()

    # --- TAHMİN EDİLEN DEĞERLER GRAFİĞİ ---
    plt.figure(figsize=(12, 5))
    for i in range(len(close_prices) - 1):
        plt.plot(time_series[i:i + 2], close_prices[i:i + 2], color=pred_colors[i])  # Çizgiyi çizer
    plt.scatter(time_series, close_prices, c=pred_colors, label="Tahmin Edilen Değerler", alpha=0.7, edgecolors='black')
    plt.title("Tahmin Edilen Değerler Grafiği")
    plt.xlabel("Zaman")
    plt.ylabel("Kapanış (Close) Fiyatı")
    plt.legend()
    plt.show()

    cm = confusion_matrix(y_test_labels, y_pred_labels, labels=le.classes_)
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt=".2f", cmap="Greens",
                xticklabels=le.classes_, yticklabels=le.classes_)
    plt.title("Konfüzyon Matrisi")
    plt.xlabel("Tahmin Edilen Etiketler")
    plt.ylabel("Gerçek Etiketler")
    plt.show()

def predict_single_row(input_df, window_size=TIMESTEP):
    """
    Belirtilen pencere boyutuna göre tek bir örnek üzerinden tahmin gerçekleştirir.
    :param input_df: pandas.DataFrame : Eğitim verisine uygun bir veri kümesi
    :param window_size: int : Pencere boyutu
    :return: str : Tahmin edilen sınıf etiketi
    """
    if len(input_df) < window_size:
        raise ValueError(
            f"Girdi veri çerçevesinin uzunluğu ({len(input_df)}) belirtilen pencere boyutundan ({window_size}) küçük olamaz.")

    scaler = joblib.load('Data/Model/scaler.pkl')
    model = load_model('Data/Model/tradeai_model.keras')
    le = joblib.load('Data/Model/label_encoder.pkl')

    input_scaled = scaler.transform(input_df[-window_size:])
    input_sequence = np.expand_dims(input_scaled, axis=0)

    prediction = model.predict(input_sequence)
    predicted_class = np.argmax(prediction)
    predicted_class_label = le.inverse_transform([predicted_class])[0]

    return predicted_class_label

# =============================================================================
# Ana Menü
# =============================================================================
def main():
    """
    Uygulama için ana menü.
    """
    print("0: Araclar.Araclar.create_dataset()\n1: create_model_best_parametre()\n2: create_model_best_model()\n3: test_model()")
    menu_input = input("Menu: ")
    for num in menu_input:
        if num == '0':
            Araclar.Araclar.create_dataset()
        elif num == '1':
            create_model_best_parametre()
        elif num == '2':
            create_model_best_model()
        elif num == '3':
            test_model()
        else:
            print('Hatalı kod!')

if __name__ == '__main__':
    main()