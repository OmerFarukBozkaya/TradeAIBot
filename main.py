from Binance import Binance
from Stratejiler import Al_Sat

binance = Binance()
alsat = Al_Sat()


alsat.dynamic_strategy(coinlist=binance.secili_list(),periyot="5m",gercek=False,sonislem="SAT",nakit=100)