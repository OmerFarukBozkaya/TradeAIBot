import numpy as np
import pandas as pd
import os

from keras_tuner import RandomSearch
from tensorflow.python.keras.layers import GlobalAveragePooling1D

import Araclar
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
import matplotlib.pyplot as plt

import joblib
import seaborn as sns
import keras_tuner as kt
from keras.src.layers import MultiHeadAttention, LayerNormalization

from sklearn.preprocessing import StandardScaler, LabelEncoder, label_binarize
from sklearn.utils.class_weight import compute_class_weight
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (confusion_matrix, classification_report, precision_score, recall_score, f1_score, roc_curve, auc )
from sklearn.decomposition import PCA

from tensorflow.keras.models import Sequential, load_model,Model
from tensorflow.keras.layers import GRU, Dense, Dropout, Conv1D, MaxPooling1D, Flatten, BatchNormalization, Bidirectional, Input, Conv1D, BatchNormalization, MaxPooling1D, Bidirectional, LSTM, Dropout, Dense, Multiply, Permute, Lambda, Flatten, Add, Activation, Concatenate
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.regularizers import l2
from tensorflow.keras.callbacks import EarlyStopping
import tensorflow.keras.backend as K

from tcn import TCN

# Ayarı değiştir
pd.set_option('display.max_columns', None)
drop_columns = ['timestamp', 'open', 'high', 'low', 'fark', 'rsi', 'ema21', 'ema7', 'sma50', 'sma200',
                'macd_val', 'macd_signal', 'bb_bot', 'bb_mid', 'bb_top', 'tso_val', 'local_min_max',
                'ma_cross', 'dmo', 'vmzi', 'adx', 'bb_adx', 'macd', 'squeeze_momentum', 'tso','volatility']
timestep = 200

def create_model_best_parametre():
    # <Veri yükleme>
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-6000:, :]  # Son 2000 veriyi al
    data = data.astype(np.float32)
    # </Veri yükleme>

    # <Kullanılacak özellikler ve hedef değişken>
    x = data.drop(drop_columns, axis=1)
    y = data['local_min_max']
    y.replace({1:'BUY',-1:'SELL',0:'False'},inplace=True)

    """
    # <Yeni özellikler>
    # 1. Log Getiri: Bir önceki kapanışa göre logaritmik değişim
    x['log_return'] = np.log(x['close'] / x['close'].shift(1))

    # 2. Volatilite: Örneğin 20 periyotluk log getirilerin standart sapması
    x['volatility'] = x['log_return'].rolling(window=20).std()

    x=x.dropna()
    # </Yeni özellikler>
    """
    # </Kullanılacak özellikler ve hedef değişken>

    # <Hedef değişkeni encode et>
    le = LabelEncoder()
    y = le.fit_transform(y)
    # </Hedef değişkeni encode et>

    # <Özellik korelasyon matrisi>
    plt.figure(figsize=(12, 10))
    sns.heatmap(x.corr(), annot=True, fmt='.2f', cmap='coolwarm')
    plt.show()
    # </Özellik korelasyon matrisi>

    # <Normalizasyon>
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(x)
    # </Normalizasyon>

    # <Dimensionality Reduction>
    from sklearn.decomposition import PCA

    pca = PCA(n_components=0.95)  # Varyansın %95'ini koruyacak bileşen sayısı
    X_pca = pca.fit_transform(X_scaled)

    print("Özellik sayısı (orijinal):", x.shape[1])
    print("Özellik sayısı (PCA sonrası):", X_pca.shape[1])

    pca = PCA(n_components=X_pca.shape[1])
    X_pca2 = pca.fit_transform(X_scaled)

    ## PCA bileşenlerinin yükleri
    loadings = pca.components_.T  # Her sütun bir PCA bileşenidir, her satır ise orijinal bir özellik
    loadings_df = pd.DataFrame(loadings, index=x.columns, columns=[f'PC{i + 1}' for i in range(X_pca.shape[1])])

    feature_importance = loadings_df.abs().sum(axis=1)

    ## Özellikleri en önemliden en önemsiz'e doğru sırala
    feature_importance_sorted = feature_importance.sort_values(ascending=False)

    print(feature_importance_sorted)
    # </Dimensionality Reduction>

    # <Class weight hesaplama>
    class_weights = compute_class_weight('balanced', classes=np.unique(y), y=y)
    class_weight_dict = {i: class_weights[i] for i in range(len(class_weights))}
    # </Class weight hesaplama>

    # <Zaman serisi penceresi (120 zaman adımı geriye bak)>
    timestep = 200
    X_sequences = []
    y_sequences = []

    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y[i])

    X_sequences, y_sequences = np.array(X_sequences), np.array(y_sequences)
    # </Zaman serisi penceresi (120 zaman adımı geriye bak)>

    # <Veri setini bölme (%80 eğitim, %20 test)>
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]
    # </Veri setini bölme (%80 eğitim, %20 test)>

    # <Modelleme> Burada model oluşturulur ve modelin en iyi hangi parametrelerle çalıştığı tespit edilir.
    def build_model(hp):
        inputs = Input(shape=(timestep, X_train.shape[2]))

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
        x = LayerNormalization(epsilon=1e-6)(x + attention_output)  # Residual bağlantı

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

    # Hiperparametre optimizasyonu
    tuner = kt.RandomSearch(
        build_model, objective='val_accuracy', max_trials=20, executions_per_trial=1,
        directory='ktuner_dir', project_name='tradeai_model_tuning'
    )
    tuner.search(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2, verbose=1)
    best_hps = tuner.get_best_hyperparameters(num_trials=1)[0]

    print("En iyi hiperparametreler:")
    print(f"Conv Filters: {best_hps.get('conv_filters')}")
    print(f"Kernel Size: {best_hps.get('kernel_size')}")
    print(f"LSTM Units 1: {best_hps.get('lstm_units')}")
    print(f"LSTM Units 2: {best_hps.get('lstm_units2')}")
    print(f"Dense Units: {best_hps.get('dense_units')}")
    print(f"Dropout Rate 1: {best_hps.get('dropout_rate')}")
    print(f"Dropout Rate 2: {best_hps.get('dropout_rate2')}")
    print(f"Learning Rate: {best_hps.get('learning_rate')}")

    # En iyi modeli al ve yeniden eğit
    model = tuner.hypermodel.build(best_hps)
    history = model.fit(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2)

    # Modelin eğitim geçmişini al
    history_dict = history.history

    # Eğitim ve doğrulama kayıpları
    loss_values = history_dict["loss"]
    val_loss_values = history_dict["val_loss"]

    # Eğitim ve doğrulama doğrulukları
    acc_values = history_dict["accuracy"]
    val_acc_values = history_dict["val_accuracy"]

    # Epoch sayısını belirle
    epochs = range(1, len(loss_values) + 1)
    # </Modelleme>

    # <Görselleştirme>
    # Kayıp grafiği
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(epochs, loss_values, "bo-", label="Eğitim Kaybı")
    plt.plot(epochs, val_loss_values, "ro-", label="Doğrulama Kaybı")
    plt.xlabel("Epoch")
    plt.ylabel("Kayıp")
    plt.title("Eğitim ve Doğrulama Kaybı")
    plt.legend()


    # Doğruluk grafiği
    plt.subplot(1, 2, 2)
    plt.plot(epochs, acc_values, "bo-", label="Eğitim Doğruluğu")
    plt.plot(epochs, val_acc_values, "ro-", label="Doğrulama Doğruluğu")
    plt.xlabel("Epoch")
    plt.ylabel("Doğruluk")
    plt.title("Eğitim ve Doğrulama Doğruluğu")
    plt.legend()

    plt.show()
    # </Görselleştirme>

    # Modelin test doğruluğunu kontrol etme
    test_loss, test_accuracy = model.evaluate(X_test, y_test)
    print(f'Test Accuracy: {test_accuracy:.4f}')

    if (input("Kayit et : ") == "1"):
        # Modelin kayit edilmesi
        os.makedirs('Data/Model', exist_ok=True)
        model.save('Data/Model/tradeai_model.keras')
        joblib.dump(scaler, 'Data/Model/scaler.pkl')
        joblib.dump(le, 'Data/Model/label_encoder.pkl')
    else:
        exit(0)

def create_model_best_model():
    # Veri yükleme
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-6000:, :]  # Son 6000 veri alınır
    data = data.astype(np.float32)

    # Kullanılmayacak sütunlar

    x = data.drop(drop_columns, axis=1)
    y = data['local_min_max']

    # Özellik korelasyon matrisi görselleştirme
    plt.figure(figsize=(12, 10))
    sns.heatmap(pd.concat([x, y], axis=1).corr(), annot=True, fmt='.2f', cmap='coolwarm')
    plt.title("Özellik Korelasyon Matrisi")
    plt.show()

    # Hedef değişkenin encode edilmesi
    y.replace({1: 'BUY', -1: 'SELL', 0: 'False'}, inplace=True)
    le = LabelEncoder()
    y = le.fit_transform(y)

    # Normalizasyon
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(x)

    # Dimensionality Reduction (PCA) - örnek bilgi için
    pca = PCA(n_components=0.95)
    X_pca = pca.fit_transform(X_scaled)
    print("Özellik sayısı (orijinal):", x.shape[1])
    print("Özellik sayısı (PCA sonrası):", X_pca.shape[1])

    pca = PCA(n_components=X_pca.shape[1])
    X_pca2 = pca.fit_transform(X_scaled)

    ## PCA bileşenlerinin yükleri
    loadings = pca.components_.T  # Her sütun bir PCA bileşenidir, her satır ise orijinal bir özellik
    loadings_df = pd.DataFrame(loadings, index=x.columns, columns=[f'PC{i + 1}' for i in range(X_pca.shape[1])])

    feature_importance = loadings_df.abs().sum(axis=1)

    ## Özellikleri en önemliden en önemsiz'e doğru sırala
    feature_importance_sorted = feature_importance.sort_values(ascending=False)

    print(feature_importance_sorted)

    # Zaman serisi penceresi (örneğin, 120 adım)
    X_sequences = []
    y_sequences = []

    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y[i])

    X_sequences, y_sequences = np.array(X_sequences), np.array(y_sequences)

    # Veri setini %80 eğitim, %20 test olarak bölme
    train_size = int(len(X_sequences) * 0.8)
    X_train, X_test = X_sequences[:train_size], X_sequences[train_size:]
    y_train, y_test = y_sequences[:train_size], y_sequences[train_size:]

    # ------------------------- Farklı Model Varyantları -------------------------
    def v0():
        inputs = Input(shape=(timestep, X_train.shape[2]))

        # CNN Katmanı
        x = Conv1D(filters=64, kernel_size=7, activation='relu', padding='same')(inputs)
        x = BatchNormalization()(x)
        x = MaxPooling1D(pool_size=2)(x)

        # GRU Katmanları
        x = Bidirectional(GRU(128, return_sequences=True))(x)
        x = Dropout(0.4)(x)
        x = Bidirectional(GRU(128, return_sequences=True))(x)

        # Attention Mekanizması
        attention_output = MultiHeadAttention(num_heads=2, key_dim=31)(x, x)
        x = LayerNormalization(epsilon=1e-6)(attention_output + x)  # Residual connection

        # Sınıflandırma Katmanları
        x = Flatten()(x)
        x = Dense(32, activation='relu')(x)
        x = Dropout(0.3)(x)
        outputs = Dense(3, activation='softmax')(x)

        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.00021348),
                      metrics=['accuracy'])
        return model

    def v1():
        inputs = Input(shape=(timestep, X_train.shape[2]))
        x = Conv1D(filters=128, kernel_size=5, activation='relu', padding='same')(inputs)
        x = BatchNormalization()(x)
        x = MaxPooling1D(pool_size=2)(x)

        # Self-Attention Katmanı
        attention_output = MultiHeadAttention(num_heads=4, key_dim=64)(x, x)
        attention_output = LayerNormalization(epsilon=1e-6)(attention_output)
        x = x + attention_output  # Residual Connection

        x = Flatten()(x)
        x = Dense(64, activation='relu')(x)
        x = Dropout(0.4)(x)
        x = Dense(3, activation='softmax')(x)

        model = Model(inputs, x)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.0005),
                      metrics=['accuracy'])
        return model

    def v2():
        def transformer_block(x, num_heads=4, ff_dim=64, dropout=0.1):
            # Self-attention bloğu
            attn_output = MultiHeadAttention(num_heads=num_heads, key_dim=ff_dim)(x, x)
            attn_output = Dropout(dropout)(attn_output)
            x_attn = LayerNormalization(epsilon=1e-6)(x + attn_output)

            # Feed-forward ağı bloğu
            ffn_output = Dense(ff_dim, activation="relu")(x_attn)
            ffn_output = Dense(int(x_attn.shape[-1]))(ffn_output)
            x_out = LayerNormalization(epsilon=1e-6)(x_attn + ffn_output)
            return x_out

        inputs = Input(shape=(120, 64))
        x_transformer = transformer_block(inputs)

        # Debug: Tip kontrolü
        print("Transformer block output type:", type(x_transformer))
        print("x_transformer:", x_transformer)

        x_pooled = GlobalAveragePooling1D()(x_transformer)
        x_dense = Dense(64, activation="relu")(x_pooled)
        outputs = Dense(3, activation="softmax")(x_dense)

        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.0005),
                      metrics=['accuracy'])
        return model

    def v3():
        inputs = Input(shape=(timestep, X_train.shape[2]))

        # İki katmanlı Bidirectional LSTM
        x = Bidirectional(LSTM(128, return_sequences=True))(inputs)
        x = Dropout(0.3)(x)
        x = Bidirectional(LSTM(128, return_sequences=True))(x)

        # Self-Attention katmanı
        attention = MultiHeadAttention(num_heads=4, key_dim=64)(x, x)
        x = LayerNormalization(epsilon=1e-6)(x + attention)

        # Sonuçların flatten edilmesi ve sınıflandırma
        x = Flatten()(x)
        x = Dense(64, activation='relu')(x)
        x = Dropout(0.4)(x)
        outputs = Dense(3, activation='softmax')(x)

        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.0005),
                      metrics=['accuracy'])
        return model

    # Modelleri bir sözlükte saklama
    models = {
        'Model v0': v0(),
        'Model v1': v1(),
        #'Model v2': v2(),
        #'Model v3': v3()
    }
    def best_model_1_1():
        inputs = Input(shape=(timestep, X_train.shape[2]))
        x = Conv1D(filters=128, kernel_size=5, activation='relu', padding='same')(inputs)
        x = BatchNormalization()(x)
        x = MaxPooling1D(pool_size=2)(x)

        # Self-Attention Katmanı
        attention_output = MultiHeadAttention(num_heads=4, key_dim=64)(x, x)
        attention_output = LayerNormalization(epsilon=1e-6)(attention_output)
        x = x + attention_output  # Residual Connection

        x = Flatten()(x)
        x = Dense(64, activation='relu')(x)
        x = Dropout(0.4)(x)
        x = Dense(3, activation='softmax')(x)

        model = Model(inputs, x)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.0005),
                      metrics=['accuracy'])
        return model
    def best_model_1_2():
        inputs = Input(shape=(timestep, X_train.shape[2]))

        # CNN Katmanı
        x = Conv1D(filters=128, kernel_size=5, activation='relu', padding='same')(inputs)
        x = BatchNormalization()(x)
        x = MaxPooling1D(pool_size=2)(x)

        # GRU Katmanları
        x = Bidirectional(GRU(128, return_sequences=True))(x)
        x = Dropout(0.3)(x)
        x = Bidirectional(GRU(64, return_sequences=True))(x)

        # Attention Mekanizması
        attention_output = MultiHeadAttention(num_heads=4, key_dim=64)(x, x)
        x = LayerNormalization(epsilon=1e-6)(attention_output + x)  # Residual connection

        # Sınıflandırma Katmanları
        x = Flatten()(x)
        x = Dense(64, activation='relu')(x)
        x = Dropout(0.4)(x)
        outputs = Dense(3, activation='softmax')(x)

        model = Model(inputs, outputs)
        model.compile(loss='sparse_categorical_crossentropy', optimizer=Adam(learning_rate=0.0005),
                      metrics=['accuracy'])
        return model

    # ------------------------- Model Eğitim, Değerlendirme ve ROC Grafikleri -------------------------

    results = {}  # Model doğruluklarını saklamak için

    for name, model in models.items():
        print(f"\n=== {name} Modeli Eğitiliyor ===")
        history = model.fit(X_train, y_train, epochs=50, batch_size=64, validation_split=0.2, verbose=1)

        test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
        results[name] = test_accuracy
        print(f"{name} Test Accuracy: {test_accuracy:.4f}")

        # Tahminler
        y_pred = model.predict(X_test)
        y_pred_classes = np.argmax(y_pred, axis=1)

        # Label Encoder'ı ters çevirerek gerçek etiketlere ulaş
        true_labels = le.inverse_transform(y_test)
        predicted_labels = le.inverse_transform(y_pred_classes)

        # Confusion Matrix
        cm = confusion_matrix(true_labels, predicted_labels, labels=le.classes_)

        # Classification Report
        cr = classification_report(true_labels, predicted_labels, target_names=le.classes_, output_dict=True)

        # Confusion Matrix Görselleştirme
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=le.classes_,
                    yticklabels=le.classes_)
        plt.xlabel('Predicted')
        plt.ylabel('Actual')
        plt.title(f"{name} - Confusion Matrix")
        plt.show()

        # Classification Report'u DataFrame olarak yazdır
        cr_df = pd.DataFrame(cr).transpose()
        print(f"\n{name} - Classification Report:")
        print(cr_df)

        # ROC Eğrisi Hesaplama (Çok sınıflı için OneVsRest yaklaşımı)
        n_classes = 3
        y_test_bin = label_binarize(y_test, classes=list(range(n_classes)))

        fpr = dict()
        tpr = dict()
        roc_auc = dict()

        for i in range(n_classes):
            fpr[i], tpr[i], _ = roc_curve(y_test_bin[:, i], y_pred[:, i])
            roc_auc[i] = auc(fpr[i], tpr[i])

        # Class isimlerini geri çevirme
        class_names = le.inverse_transform(list(range(n_classes)))

        # ROC eğrisini çizme
        plt.figure()
        for i in range(n_classes):
            plt.plot(fpr[i], tpr[i], label=f'Class {class_names[i]} (AUC = {roc_auc[i]:0.2f})')
        plt.plot([0, 1], [0, 1], 'k--')
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title(f'ROC Curve - {name}')
        plt.legend(loc="lower right")
        plt.show()

        # Ek değerlendirme raporu
        print(f"\n{name} için Ek Değerlendirme Raporu:")
        print(f"Test Loss: {test_loss:.4f}")
        print(f"Test Accuracy: {test_accuracy:.4f}")
        # İsterseniz burada ek metrikler (precision, recall, f1-score vb.) de raporlayabilirsiniz.

    # ------------------------- Modelleri Doğruluklarına Göre Sıralama -------------------------
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    print("\nModeller başarı oranlarına göre sıralandı:")
    for name, acc in sorted_results:
        print(f"{name}: {acc:.4f}")

    # Eğer modeli kaydetmek isterseniz (örneğin en iyi modeli):
    best_model_name = sorted_results[0][0]
    print(f"\nEn iyi model: {best_model_name} (Accuracy: {results[best_model_name]:.4f})")
    if input("Modeli kaydetmek ister misiniz? (1: Evet, diğer: Hayır): ") == "1":
        os.makedirs('Data/Model', exist_ok=True)
        models[best_model_name].save(f'Data/Model/tradeai_model.keras')
        joblib.dump(scaler, f'Data/Model/scaler.pkl')
        joblib.dump(le, f'Data/Model/label_encoder.pkl')
    else:
        exit(0)

def test_model_eski():
    # Önceden eğitilmiş bileşenlerin yüklenmesi
    on_ek=input('Model on eki: ')
    scaler = joblib.load(f'Data/Model/{on_ek}scaler.pkl')
    model = load_model(f'Data/Model/{on_ek}tradeai_model.keras')
    le = joblib.load(f'Data/Model/{on_ek}label_encoder.pkl')

    # Veri yükleme
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-1000000:, :]  # Son 2000 veriyi al
    data = data.astype(np.float32)

    # Kullanılacak özellikler ve hedef değişken
    x = data.drop(drop_columns, axis=1)
    y = data['local_min_max']
    y.replace({1: 'BUY', -1: 'SELL', 0: 'False'}, inplace=True)

    # Hedef değişkeni encode et
    y = le.fit_transform(y)

    # Normalizasyon
    X_scaled = scaler.fit_transform(x)

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

    # Test verileri için tahmin yap
    y_pred_probs = model.predict(X_test)  # Model olasılık tahminleri döndürür
    y_pred = np.argmax(y_pred_probs, axis=1)  # En yüksek olasılığı alan sınıfı seç

    # Tahmin ve gerçek değerleri geri dönüştür
    y_test_labels = le.inverse_transform(y_test)  # Gerçek değerleri orijinal hale getir
    y_pred_labels = le.inverse_transform(y_pred)  # Modelin tahminlerini orijinal hale getir

    # Konfüzyon matrisi hesapla
    cm = confusion_matrix(y_test_labels, y_pred_labels, labels=['BUY', 'SELL', 'False'])
    # Konfüzyon matrisini görselleştir
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=['BUY', 'SELL', 'False'],
                yticklabels=['BUY', 'SELL', 'False'])
    plt.xlabel('Tahmin Edilen')
    plt.ylabel('Gerçek Değer')
    plt.title('Konfüzyon Matrisi')
    plt.show()

def test_model():
    # Önceden eğitilmiş bileşenlerin yüklenmesi
    on_ek=input('Model on eki: ')
    scaler = joblib.load(f'Data/Model/{on_ek}scaler.pkl')
    model = load_model(f'Data/Model/{on_ek}tradeai_model.keras')
    le = joblib.load(f'Data/Model/{on_ek}label_encoder.pkl')

    # Test verilerinin yüklenmesi ve hazırlanması
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-12000:-6000,:]

    """
    print(data.info()) # Sütun isimleri, kaç tane eksik veri var, veri tipleri vb.
    print(data[kategorik_col].nunique()) # Her sütundaki eşsiz (unique) değer sayısını gösterir
    print(data.isnull().sum())  # Her sütundaki eksik değerleri gösterir
    print(data.dtypes)  # Her sütunun veri tipini gösterir
    """

    # Bu sütunları float32'ye çevir
    data = data.astype(np.float32)

    # Özelliklerin ve hedefin seçilmesi
    X = data.drop(drop_columns, axis=1)
    y = data['local_min_max']
    y.replace({1:'BUY',-1:'SELL',0:'False'},inplace=True)

    # Etiket kodlaması (Eğitim sırasında öğrenilen parametrelerle)

    try:
        y_encoded = le.transform(y)
    except ValueError as e:
        print(f"Label encoding hatası: {e}")
        return

    # Özelleklerin normalizasyonu (Eğitim scaler'ı kullanarak)
    X_scaled = scaler.transform(X)

    # Zaman serisi penceresi oluşturma
    X_sequences = []
    y_sequences = []

    for i in range(timestep, len(X_scaled)):
        X_sequences.append(X_scaled[i - timestep:i])
        y_sequences.append(y_encoded[i])

    X_test = np.array(X_sequences)
    y_test = np.array(y_sequences)

    # Model değerlendirme
    test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
    print(f"\n{'=' * 40}")
    print(f"Test Doğruluğu: {test_accuracy:.4f}")
    print(f"Test Kaybı: {test_loss:.4f}")
    print(f"{'=' * 40}\n")

    # Tahminlerin oluşturulması
    y_pred = np.argmax(model.predict(X_test), axis=1)
    y_test_labels = le.inverse_transform(y_test)
    y_pred_labels = le.inverse_transform(y_pred)

    # Detaylı metrikler
    print("Sınıflandırma Raporu:")
    print(classification_report(
        y_test_labels,
        y_pred_labels,
        target_names=le.classes_,
        digits=4
    ))

    # Precision, Recall, F1 Score
    precision = precision_score(y_test, y_pred, average='weighted')
    recall = recall_score(y_test, y_pred, average='weighted')
    f1 = f1_score(y_test, y_pred, average='weighted')

    print(f"\nWeighted Ortalama Metrikler:")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")
    print(f"F1 Score: {f1:.4f}")

    # Normalleştirilmiş Konfüzyon Matrisi
    cm = confusion_matrix(y_test_labels, y_pred_labels, labels=le.classes_)

    plt.figure(figsize=(10, 8))
    sns.heatmap(
        cm,
        annot=True,
        fmt=".2f",
        cmap="Greens",
        xticklabels=le.classes_,
        yticklabels=le.classes_
    )
    plt.title("Konfüzyon Matrisi")
    plt.xlabel("Tahmin Edilen Etiketler")
    plt.ylabel("Gerçek Etiketler")
    plt.show()

    # Sınıf Dağılım Görselleştirmesi
    plt.figure(figsize=(8, 5))
    sns.countplot(x=y_test_labels, order=le.classes_)
    plt.title("Test Verisindeki Sınıf Dağılımı")
    plt.xlabel("İşlem Sinyalleri")
    plt.ylabel("Adet")
    plt.show()

def predict_single_row(input_df):
    """

    :param input_df: pandas.DataFrame()
    :return:
    """
    # Model ve scaler'ı yükle
    scaler = joblib.load('Data/scaler.pkl')
    model = load_model('Data/tradeai_model.keras')
    le = joblib.load('Data/label_encoder.pkl')

    # Normalizasyon
    input_scaled = scaler.transform(input_df)

    # Modelin beklediği şekle getirme (120 zaman adımı gerekiyor)
    input_sequence = np.tile(input_scaled, (timestep, 1))  # 120 zaman adımı olacak şekilde kopyala
    input_sequence = np.expand_dims(input_sequence, axis=0)  # Model için (1, 120, feature_sayısı) şekline getir

    # Tahmin yap
    prediction = model.predict(input_sequence)
    predicted_class = np.argmax(prediction)

    # Etiketleri geri çevir
    predicted_class_label = le.inverse_transform([predicted_class])
    return predicted_class_label

if __name__=='__main__':
    #Araclar.Araclar.create_dataset()
    print("1: create_model_best_parametre()\n2: create_model_best_model()\n3: test_model()")
    menu_num=list(input("Menu: "))
    for num in menu_num:
        if num=='1':
            create_model_best_parametre()
        elif num=='2':
            create_model_best_model()
        elif num=='3':
            test_model()
        else:
            print('Hatali kod !')

    """
    # Tahmini al
    data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
    data = data.iloc[-500:-499, :]  # Son 2000 veriyi al
    data = data.astype(np.float32)
    print(data)
    sample_input=data
    prediction_result = predict_single_row(sample_input)
    print("Tahmin Sonucu:", prediction_result)
    """
