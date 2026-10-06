#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
MARTINGALE UNIVERSAL BACKTEST FRAMEWORK
============================================================
Прогоняет систему "мартингейл" на всех инструментах и таймфреймах.
Сохраняет положительные результаты в Excel, строит графики анализа и эквити.
"""

import os
import json
import random
import statistics
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# ============================================================
#  КОНФИГУРАЦИЯ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 10
    spread_points: float = 2.0
    commission_per_lot: float = 0.0
    history_from: Optional[str] = None
    history_to:   Optional[str] = None

@dataclass
class ComboResult:
    symbol: str
    timeframe: str
    cycles: int = 0
    wins: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    max_equity_drop: float = 0.0
    profit_factor: float = 0.0
    safety_score: float = 0.0
    history_bars: int = 0
    equity_history: List[float] = field(default_factory=list)

# ============================================================
#  ГЕНЕРАТОР СИНТЕТИЧЕСКИХ ДАННЫХ
# ============================================================
def generate_synthetic_prices(n: int, volatility: float = 0.0005,
                              drift: float = 0.0, seed: int = 42) -> List[float]:
    random.seed(seed)
    prices = [1.0]
    for _ in range(n - 1):
        change = random.gauss(drift, volatility)
        prices.append(max(0.0001, prices[-1] * (1 + change)))
    return prices

# ============================================================
#  ЯДРО БЭКТЕСТА
# ============================================================
def run_backtest(prices: List[float], symbol: str, timeframe: str,
                 cfg: Config) -> ComboResult:
    result = ComboResult(symbol=symbol, timeframe=timeframe, history_bars=len(prices))
    i = 0
    current_equity = 0.0
    equity_history = [0.0]
    peak_equity = 0.0
    
    while i < len(prices) - 1:
        positions = []
        cycle_peak = 0.0
        closed_this_cycle = False
        
        entry_price = prices[i]
        lot = cfg.start_lot
        direction = 1
        positions.append((lot, direction, entry_price))
        i += 1
        
        while i < len(prices) and len(positions) <= cfg.max_positions and not closed_this_cycle:
            current_price = prices[i]
            
            # --- НОРМАЛИЗАЦИЯ ПРОФИТА ---
            # Для крипты не нужен множитель 100000, так как цена сама по себе большая.
            # Для форекса/металлов 100000 корректно (превращает разницу цен в пункты).
            is_crypto = any(c in symbol.upper() for c in ['BITCOIN', 'ETH', 'BTC', 'CRYPTO'])
            multiplier = 1.0 if is_crypto else 100000.0
            
            total_profit = sum(((current_price - open_px) * dirn) * vol * multiplier
                               for vol, dirn, open_px in positions)
            total_profit -= cfg.commission_per_lot * sum(v for v, _, _ in positions)
            
            if total_profit > 0:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                result.wins += 1
                break
            
            if len(positions) >= cfg.max_positions:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                break
            
            sum_volumes = sum(v for v, _, _ in positions)
            new_lot = round(sum_volumes * cfg.multiplier, 2)
            positions.append((new_lot, -direction, current_price))
            i += 1
            
        result.cycles += 1
        peak_equity = max(peak_equity, current_equity)
        result.max_equity_drop = max(result.max_equity_drop, peak_equity - current_equity)
        if not closed_this_cycle: i += 1

    result.max_drawdown = result.max_equity_drop
    result.equity_history = equity_history
    
    gross_profit = max(0.0, result.total_profit)
    gross_loss = abs(min(0.0, result.total_profit))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
    win_rate = (result.wins / result.cycles) if result.cycles > 0 else 0.0
    result.safety_score = (win_rate * result.profit_factor) / (result.max_drawdown + 1.0)
    
    return result

# ============================================================
#  ДАННЫЕ
# ============================================================
def get_prices_mt5(symbol: str, timeframe: str, cfg: Config) -> Optional[List[float]]:
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(): return None
        tf_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1}
        tf = tf_map.get(timeframe)
        if not tf: return None
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 5000)
        mt5.shutdown()
        return [float(r["close"]) for r in rates] if rates is not None else None
    except: return None

def get_prices(symbol: str, timeframe: str, cfg: Config, use_real: bool) -> List[float]:
    if use_real:
        prices = get_prices_mt5(symbol, timeframe, cfg)
        if prices: return prices
    return generate_synthetic_prices(2000, volatility=0.0005, seed=hash(symbol + timeframe) % 10000)

# ============================================================
#  АНАЛИЗ И ОТЧЁТ
# ============================================================
def save_performance_analysis(positive_results: List[ComboResult], output_dir: str):
    if not positive_results: return
    df = pd.DataFrame([asdict(r) for r in positive_results])
    
    # 1. Risk vs Reward
    plt.figure(figsize=(10, 6))
    plt.scatter(df['max_drawdown'], df['total_profit'], alpha=0.6)
    plt.title("Risk vs Reward (Positive Results)")
    plt.xlabel("Max Drawdown")
    plt.ylabel("Total Profit")
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, "analysis_risk_reward.png"))
    plt.close()
    
    # 2. Profit by Symbol
    plt.figure(figsize=(12, 6))
    df.groupby('symbol')['total_profit'].mean().plot(kind='bar')
    plt.title("Average Profit by Symbol")
    plt.ylabel("Avg Total Profit")
    plt.savefig(os.path.join(output_dir, "analysis_profit_by_symbol.png"))
    plt.close()

def save_positive_results_to_excel(positive_results: List[ComboResult], output_dir: str):
    df = pd.DataFrame([asdict(r) for r in positive_results])
    df = df.drop(columns=['equity_history'], errors='ignore')
    df.to_excel(os.path.join(output_dir, "positive_backtest_results.xlsx"), index=False)
    print(f"✅ Положительные результаты сохранены в Excel.")

# ============================================================
#  MAIN
# ============================================================
def main():
    cfg = Config()
    symbols = ['XAGUSD', 'XAUUSD', 'XAGAUD', 'XAGEUR', 'XAUAUD', 'XAUEUR', 'XAUGBP', 'XAUJPY', 'XAUCNH', 'XAGJPY', 'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY', 'EURNOK', 'EURNZD', 'EURSEK', 'EURSGD', 'EURUSD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'EURTRY', 'GBPNZD', 'GBPSGD', 'GBPUSD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDSGD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDCNH', 'USDJPY', 'USDMXN', 'USDNOK', 'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'USDTHB', 'USDHKD', 'USDUSC', 'USDAED', 'SPCUSD', 'USOUSD', 'JPCUSD', 'GLDUSD', 'BRN', 'NG', 'USDInd', 'WTI', 'ARABICA', 'COCOA', 'COPPER', 'CORN', 'COTTON', 'ROBUSTA', 'SOYBEAN', 'SUGAR', 'USAHO', 'WHEAT', 'GOLDInd', 'GER40', 'CN50', 'FRA40', 'NAS100', 'SPN35', 'UK100', 'US30', 'AU200', 'EU50', 'HK50', 'US500', 'JP225', 'NETH25', 'RUS2000', 'US400', 'CHINAH', 'SG20', 'TWN', 'AAVE', 'BITCOIN', 'BITCOIN CASH', 'CARDANO', 'CHAINLINK', 'DOGECOIN', 'ETHEREUM', 'LITECOIN', 'POLKADOT', 'POLYGON', 'RIPPLE', 'SOLANA', 'STELLAR', 'TRON', 'UNISWAP', 'AVALANCH', 'AXS', 'BNB', 'COSMOS', 'PYTH', 'ILLUVIUM', 'INJ', 'RENDER', 'TRUMP', 'SUI', 'HEDERA', 'NEAR', 'APTOS', 'ARBITRUM', 'PAXG', 'GRAM', '3D SYSTEMS CORP CFD', '3M CO CFD', 'ABBOTT LABS CFD', 'ABBVIE CFD', 'ACCENTURE PLC-A CFD', 'ADOBE CFD', 'ADT CFD', 'ADV MICRO DEVICE CFD', 'ADVANCE AUTO PAR CFD', 'AES CORP CFD', 'AFLAC CFD', 'AGILENT TECH CFD', 'AIR PRODS & CHEM CFD', 'AIRBNB CFD', 'AKAMAI TECHNOLOG CFD', 'ALASKA AIR GROUP CFD', 'ALBEMARLE CORP CFD', "ALEXANDER'S INC CFD", 'ALEXANDRIA REAL CFD', 'ALIBABA GRP-ADR CFD', 'ALIGN TECHNOLOGY CFD', 'ALLEGION PLC CFD', 'ALLIANT ENERGY CFD', 'ALLSTATE CFD', 'ALPHABET INC-C CFD', 'ALPHABET-A CFD', 'ALTICE USA-A CFD', 'ALTRIA GROUP CFD', 'AMAZON CFD', 'AMC ENT CFD', 'AMCOR PLC CFD', 'AMEREN CFD', 'AMERICAN AIRLINES CFD', 'AMERICAN ELECTRI CFD', 'AMERICAN EXPRESS CFD', 'AMERICAN INTERNA CFD', 'AMERICAN TOWER C CFD', 'AMERICAN WATER W CFD', 'AMERIPRISE FINAN CFD', 'AMETEK CFD', 'AMGEN CFD', 'AMPHENOL-A CFD', 'AMPLIFY ENERGY C CFD', 'ANALOG DEVICES CFD', 'AON PLC CFD', 'APA CORP CFD', 'APPLE CFD', 'APPLIED MATERIAL CFD', 'ARCHER-DANIELS CFD', 'ARGO BLOCKCHAIN CFD', 'ARISTA NETWORKS CFD', 'ARTHUR J GALLAGH CFD', 'ASML HOLDING CFD', 'ASSURANT INC CFD', 'ASTRAZENECA-ADR CFD', 'AT&T CFD', 'ATLASSIAN-A CFD', 'ATMOS ENERGY CFD', 'AURORA CANNABIS CFD', 'AUTODESK CFD', 'AUTOMATIC DATA CFD', 'AUTOZONE CFD', 'AVERY DENNISON CFD', 'BAIDU -SP ADR CFD', 'BAKER HUGHES CO CFD', 'BALL CFD', 'BANK NY MELLON CFD', 'BANK OF AMERICA CFD', 'BARCLAYS PLC CFD', 'BATH & BODY WORK CFD', 'BAXTER INTL CFD', 'BECTON DICKINSON CFD', 'BEST BUY CO CFD', 'BEYOND MEAT CFD', 'BIO-RAD LABS-A CFD', 'BIO-TECHNE CORP CFD', 'BIOGEN CFD', 'BIOMARIN PHARMAC CFD', 'BIONTECH CFD', 'BIT MINING CFD', 'BLACKBERRY LTD CFD', 'BLACKROCK CFD', 'BLACKSTONE GRO-A CFD', 'BLOOM ENERGY CFD', 'BOEING CO/THE CFD', 'BOOKING HOLDINGS CFD', 'BORGWARNER INC CFD', 'BOSTON SCIENTIFC CFD', 'BOXLIGHT CORP CFD', 'BRISTOL-MYER SQB CFD', 'BROADCOM CFD', 'BROOKFIELD INFRA CFD', 'BROWN & BROWN CFD', 'BUMBLE INC CFD', 'BUNGE LIMITED CFD', 'CADENCE DESIGN CFD', 'CAESARS ENTERTAI CFD', 'CAMDEN PROP TR CFD', 'CANAAN CFD', 'CANOPY GROWTH CORP CFD', 'CAPITAL ONE FINA CFD', 'CARDINAL HEALTH CFD', 'CARMAX INC CFD', 'CARNIVAL CORP CFD', 'CARRIER GLOB CFD', 'CATERPILLAR CFD', 'CBRE GROUP INC-A CFD', 'CDW CORP/DE CFD', 'CELANESE CORP CFD', 'CENCORA CFD', 'CENTENE CFD', 'CENTERPOINT ENER CFD', 'CF INDUSTRIES HO CFD', 'CH ROBINSON CFD', 'CHARGEPOINT HLDG CFD', 'CHARLES RIVER LA CFD', 'CHARTER COMMUN-A CFD', 'CHECK POINT SOFT CFD', 'CHEGG CFD', 'CHEVRON CFD', 'CHIPOTLE MEXICAN CFD', 'CHUBB LTD CFD', 'CHURCH & DWIGHT CFD', 'CIGNA CFD', 'CINCINNATI FIN CFD', 'CINTAS CFD', 'CIPHER MINING CFD', 'CISCO SYSTEMS CFD', 'CITIGROUP CFD', 'CITIZENS FINANCI CFD', 'CLEAN ENERGY FUELS CFD', 'CLEAN HARBORS CFD', 'CLEANSPARK CFD', 'CLOROX CO CFD', 'CLOUDFARE INC CFD', 'CME GROUP CFD', 'CMS ENERGY CFD', 'COCA-COLA CO/THE CFD', 'COCA-COLA EUROPE CFD', 'COGNIZANT TECH-A CFD', 'COINBASE CFD', 'COLGATE-PALMOLIV CFD', 'COMCAST-A CFD', 'CONAGRA BRANDS CFD', 'CONOCOPHILLIPS CFD', 'CONS EDISON CFD', 'CONSTELLATION-A CFD', 'COOPER COS CFD', 'COPART CFD', 'CORNING CFD', 'CORTEVA CFD', 'COSTAR GROUP CFD', 'COSTCO WHOLESALE CFD', 'CRISPR THERAPAUTICS CFD', 'CRONOS GROUP CFD', 'CROWDSTRIKE HO-A CFD', 'CROWN CASTLE INT CFD', 'CSX CFD', 'CUMMINS CFD', 'CVS HEALTH CFD', 'DANAHER CFD', 'DARDEN RESTAURAN CFD', 'DATADOG INC-A CFD', "DAVE & BUSTER'S CFD", 'DAVITA INC CFD', 'DEERE & CO CFD', 'DELL TECHN-C CFD', 'DELTA AIR LI CFD', 'DENTSPLY SIRONA CFD', 'DEVON ENERGY CO CFD', 'DEXCOM CFD', 'DIAMONDBACK ENER CFD', 'DIGITAL REALTY CFD', 'DOCUSIGN CFD', 'DOLLAR GENERAL C CFD', 'DOLLAR TREE CFD', 'DOMINION ENERGY CFD', "DOMINO'S PIZZA CFD", 'DOVER CORP CFD', 'DOW CFD', 'DR HORTON CFD', 'DRAFTKINGS INC CFD', 'DTE ENERGY CO CFD', 'DUKE ENERGY CFD', 'DUPONT DE NEMOUR CFD', 'DXC TECHNOLOGY C CFD', 'EASTMAN CHEMICAL CFD', 'EATON  PLC CFD', 'EBANG INTERNATIONAL CFD', 'EBAY CFD', 'ECOLAB CFD', 'EDISON INTL CFD', 'EDWARDS LIFE CFD', 'ELEVANCE HEALTH CFD', 'ELI LILLY & CO CFD', 'EMERSON ELEC CO CFD', 'ENPHASE ENERGY INC CFD', 'ENTERGY CFD', 'ENTERPRISE PRODU CFD', 'EOG RESOURCES CFD', 'EPAM SYSTEMS INC CFD', 'EQUIFAX CFD', 'EQUINIX CFD', 'EQUITY RESIDENTI CFD', 'ESSEX PROPERTY CFD', 'ESTEE LAUDER CFD', 'ETSY INC CFD', 'EVEREST GROUP CFD', 'EVERGY INC CFD', 'EVERSOURCE ENERG CFD', 'EXELON CFD', 'EXPEDIA GROUP IN CFD', 'EXPEDITORS INTL CFD', 'EXTRA SPACE STOR CFD', 'EXXON MOBIL CFD', 'F5 INC CFD', 'FACTSET RESEARCH CFD', 'FASTENAL CO CFD', 'FASTLY INC CFD', 'FED REALTY INVS CFD', 'FEDEX CFD', 'FERRARI NV CFD', 'FIDELITY NATIONA CFD', 'FIFTH THIRD BANC CFD', 'FIRSTENERGY CFD', 'FISERV CFD', 'FMC CORP CFD', 'FORD MOTOR CO CFD', 'FORTINET CFD', 'FORTUNE BRANDS INNO CFD', 'FOX  - A CFD', 'FOX CORP - B CFD', 'FRANKLIN RES INC CFD', 'FREEPORT-MCMORAN CFD', 'FUTU HOLDINGS CFD', 'GAMESTOP CFD', 'GARMIN LTD CFD', 'GARTNER INC CFD', 'GE AEROSPACE CFD', 'GE HEALTH TECH CFD', 'GEN DIGITAL CFD', 'GENERAL DYNAMICS CFD', 'GENERAL MILLS IN CFD', 'GENERAL MOTORS C CFD', 'GENUINE PARTS CO CFD', 'GILEAD SCIENCES CFD', 'GLOBAL PAYMENTS CFD', 'GLOBE LIFE INC CFD', 'GOLDMAN SACHS GP CFD', 'GREENIDGE GENE CFD', 'HALLIBURTON CO CFD', 'HARTFORD FINL SV CFD', 'HASBRO INC CFD', 'HCA HEALTHCARE I CFD', 'HENRY SCHEIN INC CFD', 'HERSHEY CO/THE CFD', 'HERTZ CFD', 'HEWLETT PACKA CFD', 'HILTON WORLDWIDE CFD', 'HIVE BLOCKCHAIN CFD', 'HOME DEPOT CFD', 'HONEYWELL INTL CFD', 'HORMEL FOODS CRP CFD', 'HOST HOTELS & RE CFD', 'HOWMET AEROSPACE CFD', 'HP CFD', 'HUMANA CFD', 'HUNT (JB) TRANS CFD', 'HUNTINGTON BANC CFD', 'HUNTINGTON INGAL CFD', 'IAC/INTERACTIVEC CFD', 'IBM CFD', 'IDEXX LABS CFD', 'ILLINOIS TOOL WO CFD', 'ILLUMINA CFD', 'INGERSOLL-RAND I CFD', 'INGREDION INCORPORATED CFD', 'INNOVATIVE CFD', 'INOVIO PHARM CFD', 'INTEL CFD', 'INTERACTIVE BROK CFD', 'INTERCONTINENTAL CFD', 'INTL FLVR & FRAG CFD', 'INTL PAPER CO CFD', 'INTUIT CFD', 'INTUITIVE SURGIC CFD', 'INVESCO LTD CFD', 'IPG PHOTONICS CFD', 'IQIYI-ADR CFD', 'IQVIA HOLDINGS I CFD', 'IRON MOUNTAIN CFD', 'JACK HENRY CFD', 'JACOBS SOLUTIONS CFD', 'JD-ADR CFD', 'JM SMUCKER CO CFD', 'JOHNSON CONTROLS CFD', 'JOHNSON&JOHNSON CFD', 'JOYY INC CFD', 'JPMORGAN CHASE CFD', 'K12 CFD', 'KEURIG DR PEPPER CFD', 'KEYCORP CFD', 'KEYSIGHT TEC CFD', 'KIMBERLY-CLARK CFD', 'KIMCO REALTY CFD', 'KINDER MORGAN IN CFD', 'KKR & CO-A CFD', 'KLA CFD', 'KONINKLIJKE PHILIPS CFD', 'KRAFT HEINZ CO/T CFD', 'KROGER CO CFD', 'KYNDRYL HOLD CFD', 'L3HARRIS TECHNOL CFD', 'LAM RESEARCH CFD', 'LAS VEGAS SANDS CFD', 'LEIDOS HOLDINGS CFD', 'LEMONADE INC CFD', 'LINCOLN NATL CRP CFD', 'LIVE NATION ENTE CFD', 'LKQ CORP CFD', 'LOCKHEED MARTIN CFD', 'LOEWS CORP CFD', "LOWE'S COS CFD", 'LUCID GROUP CFD', 'LULULEMON ATH CFD', 'LUMEN TECHNOLOGI CFD', 'LYONDELLBASELL-A CFD', 'M&T BANK CFD', 'MARATHON DIGITAL CFD', 'MARATHON PETROLE CFD', 'MARKETAXESS CFD', 'MARRIOTT INTL-A CFD', 'MARSH & MCLENNAN CFD', 'MARTIN MAR MTLS CFD', 'MARVELL TECH GRP CFD', 'MASCO CORP CFD', 'MASTERCARD-A CFD', 'MATCH GROUP INC CFD', 'MAWSON INFRASTR CFD', 'MCCORMICK-N/V CFD', 'MCDONALDS CFD', 'MCKESSON CFD', 'MEDTRONIC PLC CFD', 'MERCADOLIBRE CFD', 'MERCK & CO CFD', 'META PLATFORMS CFD', 'METLIFE CFD', 'METTLER-TOLEDO CFD', 'MGM RESORTS INTE CFD', 'MICROCHIP TECH CFD', 'MICRON TECH CFD', 'MICROSOFT CFD', 'MID-AMERICA APAR CFD', 'MODERNA INC CFD', 'MOHAWK INDS CFD', 'MOLINA HEALTHCAR CFD', 'MOLSON COORS-B CFD', 'MONDELEZ INTER-A CFD', 'MONOLITHIC POWER CFD', 'MONSTER BEVERAGE CFD', "MOODY'S CFD", 'MORGAN STANLEY CFD', 'MOSAIC CO/THE CFD', 'MOTOROLA SOLUTIO CFD', 'MSCI CFD', 'NASDAQ CFD', 'NEOGEN CFD', 'NETAPP INC CFD', 'NETEASE-ADR CFD', 'NETFLIX CFD', 'NEW ORIENTAL-ADR CFD', 'NEWELL BRANDS IN CFD', 'NEWMONT CFD', 'NEWS CORP-CL A CFD', 'NEWS CORP-CL B CFD', 'NEXTERA ENERGY CFD', 'NIKE  --B CFD', 'NIO INC CFD', 'NISOURCE INC CFD', 'NOKIA OYJ CFD', 'NORDSON CORP CFD', 'NORFOLK SOUTHERN CFD', 'NORTHERN TRUST CFD', 'NORTHROP GRUMMAN CFD', 'NORWEGIAN CRUISE CFD', 'NOVAVAX CFD', 'NRG ENERGY CFD', 'NUCOR CORP CFD', 'NVIDIA CFD', 'NVR INC CFD', 'NXP SEMICONDUCTO CFD', "O'REILLY AUTOMOT CFD", 'OATLY GROUP CFD', 'OCCIDENTAL PETE CFD', 'OKTA CFD', 'OLD DOMINION FRT CFD', 'OMNICOM GROUP CFD', 'ONEOK INC CFD', 'ORACLE CFD', 'ORGANON & CO CFD', 'OTIS WORLDWI CFD', 'PACCAR CFD', 'PACIFIC BIOSCIENCES CFD', 'PACKAGING CORP CFD', 'PALANTIR TECH CFD', 'PALO ALTO NETWOR CFD', 'PARAMOUNT GLOB-B CFD', 'PARKER HANNIFIN CFD', 'PAYCHEX CFD', 'PAYCOM SOFTWARE CFD', 'PAYPAL HOLDINGS CFD', 'PENN NATL GAMING CFD', 'PENTAIR PLC CFD', 'PEPSICO CFD', 'PFIZER CFD', 'PHILIP MORRIS IN CFD', 'PHILLIPS 66 CFD', 'PINDUODUO CFD', 'PINNACLE WEST CFD', 'PINTEREST CFD', 'PNC FINANCIAL SE CFD', 'POOL CORP CFD', 'PPG INDS CFD', 'PPL CFD', 'PRINCIPAL FINL CFD', 'PROCTER & GAMBLE CFD', 'PROGRESSIVE CFD', 'PROLOGIS CFD', 'PRUDENTL FINL CFD', 'PTC INC CFD', 'PUB SERV ENTERP CFD', 'PUBLIC STORAGE CFD', 'PULTEGROUP INC CFD', 'PVH CORP CFD', 'QORVO CFD', 'QUALCOMM CFD', 'QUANTA SERVICES CFD', 'QUANTUMSCAPE CFD', 'QUEST DIAGNOSTIC CFD', 'RALPH LAUREN COR CFD', 'RAYMOND JAMES CFD', 'RAYTHEON CO CFD', 'REALTY OME CFD', 'REGENERON PHARM CFD', 'REGIONS FINANCIA CFD', 'REPUBLIC SVCS CFD', 'RESMED CFD', 'REVVITY INC CFD', 'RINGCENTRAL IN-A CFD', 'RIOT BLOCKCHAIN CFD', 'RIVIAN AUTO CFD', 'ROBERT HALF INTL CFD', 'ROBINHOOD CFD', 'ROBLOX CFD', 'ROCKWELL AUTOMAT CFD', 'ROLLINS INC CFD', 'ROPER TECHNOLOGI CFD', 'ROSS STORES CFD', 'ROYAL CARIBBEAN CFD', 'S&P GLOBAL CFD', 'SALESFORCE CFD', 'SBA COMM CFD', 'SCHLUMBERGER LTD CFD', 'SCHRODINGER INC CFD', 'SCHWAB (CHARLES) CFD', 'SEA LTD-ADR CFD', 'SEAGATE TECHNOLO CFD', 'SEMPRA ENERGY CFD', 'SERVICENOW CFD', 'SHERWIN-WILLIAMS CFD', 'SHOPIFY CFD', 'SIMON PROPERTY CFD', 'SIRIUS XM HOLDIN CFD', 'SKYWORKS SOLUTIO CFD', 'SMITH AO CORP CFD', 'SNAP  - A CFD', 'SNOWFLAKE INC CFD', 'SOLAREDGE TECHNO CFD', 'SOUTHERN CO CFD', 'SOUTHERN COPPER CFD', 'SOUTHWEST AIR CFD', 'SPHERE 3D CORP CFD', 'SPOTIFY TECHNOLO CFD', 'STANLEY BLACK & CFD', 'STARBUCKS CFD', 'STATE ST CFD', 'STERIS PLC CFD', 'STRYKER CFD', 'SYNCHRONY FINANC CFD', 'SYSCO CFD', 'T-MOBILE US CFD', 'TAKE-TWO INTERAC CFD', 'TAL EDUCATIO-ADR CFD', 'TAPESTRY INC CFD', 'TARGET CFD', 'TE CONNECTIVITY CFD', 'TELADOC HEALTH CFD', 'TELEDYNE TECH CFD', 'TELEFLEX INC CFD', 'TENCENT MUSI-ADR CFD', 'TERADYNE INC CFD', 'TESLA CFD', 'TEXAS INSTRUMENT CFD', 'TEXTRON INC CFD', 'THERMO FISHER CFD', 'TILRAY INC CFD', 'TJX COS CFD', 'TRACTOR SUPPLY CFD', 'TRANE TECHNOLOGI CFD', 'TRANSDIGM GROUP CFD', 'TRAVELERS COS IN CFD', 'TRIMBLE INC CFD', 'TRIP GRO-ADR CFD', 'TRUIST FINANCIAL CFD', 'TSM CFD', 'TYLER TECHNOLOG CFD', 'TYSON FOODS-A CFD', 'UBER TECHNOLOGIE CFD', 'UDR INC CFD', 'ULTA BEAUTY INC CFD', 'UNDER ARMO-C CFD', 'UNDER ARMOUR-A CFD', 'UNILEVER CFD', 'UNION PAC CFD', 'UNITED AIRLINES CFD', 'UNITED PARCEL-B CFD', 'UNITED RENTALS CFD', 'UNITEDHEALTH GRP CFD', 'UP FINTECH HOLDING CFD', 'UPSTART HOLDINGS CFD', 'US BAN CFD', 'VALERO ENERGY CFD', 'VEEVA SYSTEMS-A CFD', 'VENTAS INC CFD', 'VERISIGN CFD', 'VERISK ANALYTI CFD', 'VERIZON COMMUNIC CFD', 'VERTEX PHARM CFD', 'VF CFD', 'VIASAT CFD', 'VIATRIS CFD', 'VIPSHOP HOLD CFD', 'VISA -CLASS A CFD', 'VORNADO RLTY TST CFD', 'VULCAN MATERIALS CFD', 'WABTEC CORP CFD', 'WALMART CFD', 'WALT DISNEY CO CFD', 'WARNER BROS CFD', 'WASTE MANAGEMENT CFD', 'WATERS CORP CFD', 'WEC ENERGY GROUP CFD', 'WEIBO CFD', 'WELLS FARGO & CO CFD', 'WELLTOWER CFD', 'WEST PHARMACEUT CFD', 'WESTERN DIGITAL CFD', 'WEYERHAEUSER CFD', 'WHIRLPOOL CORP CFD', 'WILLIAMS COS CFD', 'WILLIS TOWERS WA CFD', 'WIMI HOLOGRAM CFD', 'WORKDAY-A CFD', 'WR BERKLEY CORP CFD', 'WW GRAINGER INC CFD', 'WYNN RESORTS LTD CFD', 'XCEL ENERGY CFD', 'XPENG INC - ADR CFD', 'XYLEM INC CFD', 'YTE CFD', 'YUM CHINA HO CFD', 'YUM! BRANDS CFD', 'ZEBRA TECH CORP CFD', 'ZILLOW GROUP CFD', 'ZIMMER BIOMET HO CFD', 'ZIONS BANCORP NA CFD', 'ZOETIS CFD', 'ZOOM VIDEO COM-A CFD', 'ZSCALER INC CFD', 'ZTO EXPRESS-ADR CFD', 'MICROSTRATEGY CFD', 'BXP INC CFD', 'BAOZUN INC CFD', 'DAQO NEW ENERGY CFD', 'AMC NETWORKS CFD', 'ARM HOLDINGS CFD', 'MOBILEYE GLOBAL CFD', 'TRIPADVISOR INC CFD', 'SONY GROUP CORP CFD', 'ALCOA CORP CFD', 'LI AUTO CFD', 'ORASURE TECH CFD', 'SOHU COM LTD CFD', 'HERBALIFE LTD CFD', 'CLIFFS NAT CFD', 'CEMEX SAB DE CV CFD', 'DROPBOX INC CFD', 'GOODYEAR TIRE CFD', 'HARLEY-DAVIDSON CFD', 'JEFFERIES FIN CFD', 'NOV INC CFD', 'OWEN ILLINOIS CFD', 'PITNEY BOWES CFD', 'PG&E CORP CFD', 'TENET HEALTH CFD', 'WESTERN UNION CFD', 'FRESH DEL MONTE CFD', 'TEVA CFD', 'AUTOHOME CFD', 'GODADDY CFD', 'MANPOWER INC CFD', 'HELLO GROUP CFD', 'UNIVERSAL PLAY CFD', 'PETROLEO BRASIL CFD', 'PLUG POWER CFD', 'PELOTON INTERAC CFD', 'VIRGIN GALACTIC CFD', 'ULTRAPRO QQQ CFD', 'TWILIO INC CFD', 'WAYFAIR CFD', 'WIX COM LTD CFD', 'YELP INC CFD', 'AFFI MANAGERS CFD', 'ARCH CAPITAL CFD', 'AGIOS PHARMA CFD', 'AGNC INVESTMENT CFD', 'ALNYLAM PHARMA CFD', 'ANGI INC CFD', 'AMERICAN O CFD', 'AGORA INC CFD', 'DIGITAL TURBINE CFD', 'ARES CAPITAL CFD', 'ATOMERA INC CFD', 'AURINIA PHARMA CFD', 'AXON ENTERPRISE CFD', 'BEIGENE LTD CFD', 'BALLARD POWER CFD', 'BLACKBAUD INC CFD', 'BLINK CHARGING CFD', 'BOK FINANCIAL CFD', 'BRUKER CORP CFD', 'CRED ACCEPTANCE CFD', 'CARGURUS INC CFD', 'CASEYS GENERAL CFD', 'CRACKER BARREL CFD', 'COMMERCE BANC CFD', 'CONSTELL ENERGY CFD', 'COGNEX CORP CFD', 'CARLYLE GROUP CFD', 'CHURCHILL DOWNS CFD', 'CENTURY CASINOS CFD', 'COLUMBIA SPORTS CFD', 'CRESUD SACIF CFD', 'CRITEO SA CFD', 'EURONET CFD', 'ELBIT SYSTEMS CFD', 'EAST WEST CFD', 'FUELCELL CFD', 'FIRSTCASH INC CFD', 'FIBROGEN INC CFD', 'FIVE BELOW INC CFD', 'FUNKO INC CFD', 'GDS HOLDINGS CFD', 'GILAT SATELLITE CFD', 'GAMING & L CFD', 'GENTEX CORP CFD', 'GRAND CANYON CFD', 'BANK OZK CFD', 'ECHOSTAR CORP CFD', 'CASSAVA SCI CFD', 'VNET GROUP CFD', 'GENERAC CFD', 'REGENCY CFD', 'TARGA RESOURCES CFD', 'ENOVIX CORP CFD', 'UIPATH INC CFD', 'SIGMA LITHIUM CFD', 'SOLID POWER CFD', 'DIAGEO PLC CFD', 'EQUINOR ASA CFD', 'LM ERICSSON CFD', 'FRESENIUS MEDI CFD', 'GREIF INC CFD', 'GENMAB A/S CFD', 'GSK PLC CFD', 'HEICO CORP CFD', 'HALEON PLC CFD', 'HARMONY GOLD CFD', 'HSBC HOLDINGS CFD', 'INTERCON HOTELS CFD', 'LIB LATIN CL C CFD', 'LIB LATIN CL A CFD', 'LLOYDS CFD', 'NOVO NORDISK CFD', 'NATWEST GROUP CFD', 'OVINTIV INC CFD', 'PEARSON PLC CFD', 'RES BRANDS CFD', 'RELX PLC CFD', 'SHELL PLC CFD', 'SASOL LTD CFD', 'THOMSON REUT CFD', 'TENARIS SA CFD', 'VIKING THERA CFD', 'ADEIA INC CFD', 'ALPHA METALLUR CFD', 'BROWN-FORMAN CFD', 'BUILDERS FIRST CFD', 'CECO ENV CORP CFD', 'ENTEGRIS INC CFD', 'EQT CORP CFD', 'FIRST SOLAR CFD', 'NEOGENOMICS CFD', 'SNDL INC CFD', 'UNI HEALTH CFD', 'RAPID7 INC CFD', 'ALBERTSONS COS CFD', 'MEDICAL PROP CFD', 'MARAVAI CFD', 'ARCHER AVIATION CFD', 'VICI PROPERTIES CFD', 'INVITATION HOME CFD', 'FAIR ISAAC CORP CFD', 'INSULET CORP CFD', 'BROADRIDGE FIN CFD', 'LAMB WESTO CFD', 'IDEX CORP CFD', 'CHEESECAKEF CFD', 'CAMECO CORP CFD', 'REDDIT INC CFD', 'MANCHESTER CFD', 'NEXGEN ENERGY CFD', 'ROKU INC CFD', 'SOCIEDAD QUI CFD', 'TRADE DESK CFD', 'SILVER WHEATON CFD', 'TOTALENERGIES CFD', 'GRAB HOLDINGS CFD', 'EQUINOX GOLD CORP CFD', 'HYPERSCALE DATA CFD', 'BLOCK - A CFD', "CAMPBELL'S CO CFD", 'LYFT INC CFD', 'SPACEX CFD', 'NAS100U6', 'GER40U6', 'US30U6', 'SP500U6', 'GOLDZ6', 'CHCJPC', 'DJCGLD', 'DJCJPC', 'DJCSPC', 'NACJPC', 'SPCJPC']
    timeframes = ["M15", "H1"]
    use_real = True
    
    results = []
    print(f"\n🚀 ЗАПУСК БЭКТЕСТА (Реальные данные: {use_real})")
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"[{symbol:<10}| {tf:<4}] ", end="", flush=True)
            prices = get_prices(symbol, tf, cfg, use_real)
            if not prices or len(prices) < 100:
                print("недостаточно данных")
                continue
            res = run_backtest(prices, symbol, tf, cfg)
            results.append(res)
            print(f"циклов: {res.cycles} profit: {res.total_profit:.1f}")
            
    # Фильтрация
    positive_results = [r for r in results if r.total_profit > 0]
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)
    
    # Сохранение и графики
    if positive_results:
        save_positive_results_to_excel(positive_results, output_dir)
        save_performance_analysis(positive_results, output_dir)
        for r in positive_results:
            plt.figure(figsize=(10, 6))
            plt.plot(r.equity_history)
            plt.title(f"Equity: {r.symbol} {r.timeframe}")
            plt.savefig(os.path.join(output_dir, f"equity_{r.symbol}_{r.timeframe}.png"))
            plt.close()
        print(f"\n✅ Анализ завершен. Результаты в папке /results")
    else:
        print("\n❌ Нет положительных результатов для сохранения.")

if __name__ == "__main__":
    main()
