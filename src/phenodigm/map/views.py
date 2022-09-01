import io
from PIL import Image
from django.views.decorators import gzip
from django.http import StreamingHttpResponse
import threading
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
import django
from django.shortcuts import render
from folium import plugins
import folium
import base64
from .fusioncharts import FusionCharts
from .fusioncharts import FusionTable
from .fusioncharts import TimeSeries
import json
import pandas as pd
import numpy as np
import datetime
from pathlib import Path
import sys

from django.views.decorators.csrf import csrf_exempt
from prophet.serialize import model_to_json, model_from_json
import cv2 as cv
import numpy as np
import matplotlib.pyplot as plt

# 다른 패키지에 있는 모듈 가져오기
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if sys.path.count(f"{BASE_DIR}/phenoKOR") == 0: sys.path.append(f"{BASE_DIR}/phenoKOR")
if sys.path.count(f"{BASE_DIR}\\phenoKOR") == 0: sys.path.append(f"{BASE_DIR}\\phenoKOR")
import phenoKOR as pk
import data_preprocessing as dp

# 전역변수
root, middle = dp.get_info()
knps_final = dp.load_final_data("", "", True)


# 홈 페이지
@xframe_options_exempt  # iframe 허용하기 위한 태그
def index(request):
    m = folium.Map(location=[36.684273, 128.068635], zoom_start=6.5, width="100%", height="100%")  # 기본이 되는 지도 정보 가져오기

    name = dp.get_knps_name_EN()
    position = dp.get_knps_position()

    # 국립공원 수만큼 반복
    for i in range(len(name)):
        # 국립공원 대표 이미지 가져오기
        pic = base64.b64encode(open(f'../resource/{name[i]}.png', 'rb').read()).decode()
        # 국립공원 대표 이미지 클릭시 해당 분석 페이지로 이동하는 html 태그 설정
        image_tag = f'<div style="text-align:center; "><a href="http://127.0.0.1:8000/analysis/?knps={name[i]}&start_year=2003&end_year=2003&class_num=0&curve_fit=1&shape=1&threshold=0.4" target="_top"><img src="data:image/png;base64,{pic}" width="200" height="150"></a></div>'
        # iframe 생성
        iframe = folium.IFrame(image_tag, width=220, height=170)
        # html 띄울 popup 객체 생성
        popup = folium.Popup(iframe)

        # 지도에 마커 찍기
        folium.Marker(position[i],
                      popup=popup,
                      icon=folium.Icon(color='green', icon='fa-tree', prefix='fa')).add_to(m)

    plugins.LocateControl().add_to(m)  # 위치 컨트롤러 추가

    maps = m._repr_html_()  # 지도를 템플릿에 삽입하기위해 iframe이 있는 문자열로 반환 (folium)

    return render(request, 'map/index.html', {'map': maps})  # index.html에 map 변수에 maps 값 전달하기


# 분석 페이지
def analysis(request):
    property_list = ["knps", "curve_fit", "start_year", "end_year", "class_num", "threshold", "shape",
                     "AorP"]  # GET 메소드로 주고 받을 변수 이름들
    db = {}  # 데이터를 저장하고 페이지에 넘겨 줄 딕셔너리

    if request.method == 'GET':  # GET 메소드로 값이 넘어 왔다면,
        for key in property_list:
            # 값이 넘어 오지 않았다면 "", 값이 넘어 왔다면 해당하는 값을 db에 넣어줌
            db[f"{key}"] = request.GET[f"{key}"] if request.GET.get(f"{key}") else ""  # 삼항 연산자

    db['graph'] = get_chart(db) if db['shape'] == "1" else get_multi_plot(db)  # shape 값(연속, 연도)에 따라 그래프를 그려줌
    # *shape는 default: 1임
    db['dataframe'] = export_doy(db)

    # *threshold는 default : 50

    return render(request, 'map/analysis.html', db)  # 웹 페이지에 값들 뿌려주기


# 예측 페이지
def predict(request):
    property_list = ["knps", "curve_fit", "start_year", "end_year", "class_num", "threshold", "shape", "AorP"]
    db = {}

    if request.method == 'GET':
        for key in property_list:
            db[f"{key}"] = request.GET[f"{key}"] if request.GET.get(f"{key}") else ""

    db['graph'] = get_predict_chart(db) if db['shape'] == "1" else get_predict_multi_plot(db)
    db['dataframe'] = predict_export_doy(db)

    return render(request, 'map/predict.html', db)


# 페노캠 이미지 분석하는 페이지
@csrf_exempt
def phenocam(request):
    db = {}

    if request.method == 'POST':
        if request.FILES:  # input[type=file]로 값이 넘어 왔다면,
            columns = ['date', 'code', 'year', 'month', 'day', 'rcc', 'gcc']  # 파일 정보 저장에 사용할 key: value
            for key in columns:
                db[f"{key}"] = []
            info = dict(request.FILES)  # 파일 정보 담긴 딕셔너리
            imgs, img_mask = [], None  # init

            # 이미지 가져오기
            if info['imgs']:
                imgs_byte = info['imgs']  # 폴더 내에 있는 모든 파일 가져오기

                # 파일 이름에서 정보 추출하기
                for img_byte in imgs_byte:
                    filename = img_byte.name  # 파일 이름 가져오기
                    fn_split_list = filename.split("_")  # 파일 이름 _ 으로 분리
                    for i in range(4):
                        db[columns[i + 1]].append(fn_split_list[i])  # code, year, month, day 순으로 삽입
                    # datetime 넣기
                    db["date"].append(
                        pd.to_datetime(f"{fn_split_list[1]}-{fn_split_list[2]}-{fn_split_list[3]}", format="%Y-%m-%d"))

                    imgs.append(dp.byte2img(img_byte.read()))  # 바이트 파일을 이미지로 변환해 리스트에 저장

                # db['path'] = imgs_byte[0].temporary_file_path()  # 첫 이미지의 절대 경로 가져오기
                imgs = np.array(imgs)  # arr2ndarray

                # 마스크 이미지 가져오기
                if info['img_mask']:
                    img_mask = dp.byte2img(info['img_mask'][0].read())
                    img_mask = cv.resize(img_mask, (imgs[0].shape[1], imgs[0].shape[0]))  # 캔버스 그릴 때 축소해서 원본 크기로 맞춤
                    new_mask = np.where(img_mask == 255, img_mask, 0)  # 직접 그린 관심 영역 제외하고 검정색(0)으로 만들기

            # 관심 영역 이미지 구하기
            imgs_roi = []
            for img in imgs:
                img_roi = dp.load_roi(img, new_mask)
                imgs_roi.append(img_roi)
            imgs_roi = np.array(imgs_roi)

            # 관심 영역 이미지에 대한 rcc, gcc 값 구하기
            rcc_list, gcc_list = [], []
            for img_roi in imgs_roi:
                rcc, gcc = pk.get_cc(img_roi)

                rcc_list.append(rcc)
                gcc_list.append(gcc)
            db['rcc'] = rcc_list
            db['gcc'] = gcc_list

            # dataframe 만들기
            df = pd.DataFrame(columns=columns)
            for key in columns:
                df[f'{key}'] = db[f"{key}"]

            try:
                ori_df = pd.DataFrame(f"{root}{middle}data{middle}pheno_test.csv")
            except:
                ori_df = pd.DataFrame(columns=columns)

            save_df = pd.concat([ori_df, df])
            save_df.to_csv(f"{root}{middle}data{middle}pheno_test.csv", index=False)

            db['graph'] = get_chart_for_phenocam(df)

    return render(request, 'map/phenocam.html', db)


# 연속된 그래프를 그려주는 메소드
def get_chart_for_phenocam(ori_db):
    # df = dp.load_final_data(ori_db['knps'], ori_db['class_num'])  # 데이터 가져오기
    # df, df_sos = pk.curve_fit(df, ori_db)

    df = pd.read_csv(f"{root}{middle}data{middle}knps_final_analysis.csv")
    df = df[(df["code"] == ori_db["knps"]) & (df["class"] == int(ori_db["class_num"])) &
            (df['date'].str[:4] >= ori_db["start_year"]) & (df['date'].str[:4] <= ori_db["end_year"])].sort_values('date')

    data = []  # 그래프를 그리기 위한 데이터
    schema = [{"name": "Time", "type": "date", "format": "%Y-%m-%d"}, {"name": "EVI", "type": "number"}]  # 하나의 data 구조
    info_day = [None, 31, None, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # 월별 일 수 정보
    year, month, day = int(ori_db['start_year']), 1, 1  # 년월일을 알기 위한 변수

    for _ in range(len(df)):  # data에 값 채우기
        data.append([f"{year}-{month}-{day}", df.iloc[len(data)]['avg']])  # schema 형태에 맞게 데이터 추가

        day += 8  # 8일 간격씩 데이터 추가
        if month == 2:  # 2월은 윤년 여부 판단하기
            day_limit = dp.get_Feb_day(year)
        else:  # 2월이 아니면 해당 월의 일 수 가져오기
            day_limit = info_day[month]

        # 다음 월로 넘어가야 한다면,
        if day > day_limit:
            day -= day_limit  # 새로운 일
            month += 1  # 다음 월로 가기

            if month > 12:  # 다음 연도로 넘어가야 한다면,
                year += 1
                # 무조건 1월 1일부터 시작하기 때문에 month와 day를 1로 초기화
                month = 1
                day = 1

    fusionTable = FusionTable(json.dumps(schema), json.dumps(data))  # 데이터 테이블 만들기
    timeSeries = TimeSeries(fusionTable)  # 타임시리즈 만들기

    # 그래프 속성 설정하기
    timeSeries.AddAttribute('caption', f'{{"text":"EVI of {ori_db["knps"]}"}}')
    timeSeries.AddAttribute('chart',
                            f'{{"theme":"candy", "exportEnabled": "1", "exportfilename": "{ori_db["knps"]}_{ori_db["class_num"]}_{ori_db["start_year"]}_{ori_db["end_year"]}"}}')
    timeSeries.AddAttribute('subcaption', f'{{"text":"class_num : {ori_db["class_num"]}"}}')
    timeSeries.AddAttribute('yaxis', '[{"plot":{"value":"EVI"},"format":{"prefix":""},"title":"EVI"}]')

    # 그래프 그리기
    fcChart = FusionCharts("timeseries", "ex1", 960, 400, "chart-1", "json", timeSeries)

    # 그래프 정보 넘기기
    return fcChart.render()


# 연속된 그래프를 그려주는 메소드
def get_chart(ori_db):
    # df = dp.load_final_data(ori_db['knps'], ori_db['class_num'])  # 데이터 가져오기
    # df, df_sos = pk.curve_fit(df, ori_db)

    df = pd.read_csv(f"{root}{middle}data{middle}knps_final_analysis.csv")
    df = df[(df["code"] == ori_db["knps"]) & (df["class"] == int(ori_db["class_num"])) &
            (df['date'].str[:4] >= ori_db["start_year"]) & (df['date'].str[:4] <= ori_db["end_year"])].sort_values('date')

    data = []  # 그래프를 그리기 위한 데이터
    schema = [{"name": "Time", "type": "date", "format": "%Y-%m-%d"}, {"name": "EVI", "type": "number"}]  # 하나의 data 구조
    info_day = [None, 31, None, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]  # 월별 일 수 정보
    year, month, day = int(ori_db['start_year']), 1, 1  # 년월일을 알기 위한 변수

    for _ in range(len(df)):  # data에 값 채우기
        data.append([f"{year}-{month}-{day}", df.iloc[len(data)]['avg']])  # schema 형태에 맞게 데이터 추가

        day += 8  # 8일 간격씩 데이터 추가
        if month == 2:  # 2월은 윤년 여부 판단하기
            day_limit = dp.get_Feb_day(year)
        else:  # 2월이 아니면 해당 월의 일 수 가져오기
            day_limit = info_day[month]

        # 다음 월로 넘어가야 한다면,
        if day > day_limit:
            day -= day_limit  # 새로운 일
            month += 1  # 다음 월로 가기

            if month > 12:  # 다음 연도로 넘어가야 한다면,
                year += 1
                # 무조건 1월 1일부터 시작하기 때문에 month와 day를 1로 초기화
                month = 1
                day = 1

    fusionTable = FusionTable(json.dumps(schema), json.dumps(data))  # 데이터 테이블 만들기
    timeSeries = TimeSeries(fusionTable)  # 타임시리즈 만들기

    # 그래프 속성 설정하기
    timeSeries.AddAttribute('caption', f'{{"text":"EVI of {ori_db["knps"]}"}}')
    timeSeries.AddAttribute('chart',
                            f'{{"theme":"candy", "exportEnabled": "1", "exportfilename": "{ori_db["knps"]}_{ori_db["class_num"]}_{ori_db["start_year"]}_{ori_db["end_year"]}"}}')
    timeSeries.AddAttribute('subcaption', f'{{"text":"class_num : {ori_db["class_num"]}"}}')
    timeSeries.AddAttribute('yaxis', '[{"plot":{"value":"EVI"},"format":{"prefix":""},"title":"EVI"}]')

    # 그래프 그리기
    fcChart = FusionCharts("timeseries", "ex1", 960, 400, "chart-1", "json", timeSeries)

    # 그래프 정보 넘기기
    return fcChart.render()


# 연도별 그래프를 그려주는 메소드
def get_multi_plot(ori_db):
    # df = pd.read_csv(root + f"{middle}data{middle}knps_final.csv")
    # df = df[df['class'] == int(ori_db['class_num'])]
    # df = df[df['code'] == ori_db['knps']]
    #
    # df, df_sos = pk.curve_fit(df, ori_db)

    df = pd.read_csv(f"{root}{middle}data{middle}knps_final_analysis.csv")
    df = df[(df["code"] == ori_db["knps"]) & (df["class"] == int(ori_db["class_num"])) &
            (df['date'].str[:4] >= ori_db["start_year"]) & (df['date'].str[:4] <= ori_db["end_year"])].sort_values(
        'date')

    # curve fitting된 데이터 가져오기

    # 그래프 속성 및 데이터를 저장하는 변수
    db = {
        "chart": {  # 그래프 속성
            "exportEnabled": "1",
            "exportfilename": f"{ori_db['knps']}_{ori_db['class_num']}_{ori_db['start_year']}_{ori_db['end_year']}",
            "bgColor": "#262A33",
            "bgAlpha": "100",
            "showBorder": "0",
            "showvalues": "0",
            "numvisibleplot": "12",
            "caption": f"EVI of {ori_db['knps']}",
            "subcaption": f"class_num : {ori_db['class_num']}",
            "yaxisname": "EVI",
            "theme": "candy",
            "drawAnchors": "0",
            "plottooltext": "<b>$dataValue</b> EVI of $label",
        },
        "categories": [{  # X축
            "category": [{"label": str(i)} for i in range(1, 365, 8)]
        }],
        "dataset": []  # Y축
    }

    # 데이터셋에 데이터 넣기
    for now in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):  # start_year에서 end_year까지
        db["dataset"].append({
            "seriesname": str(now),  # 레이블 이름
            # 해당 연도에 시작 (1월 1일)부터 (12월 31)일까지의 EVI 값을 넣기
            "data": [{"value": i} for i in
                     df[df['date'].str[:4] == str(now)].avg]
        })

    # 그래프 그리기
    chartObj = FusionCharts('scrollline2d', 'ex1', 960, 400, 'chart-1', 'json', json.dumps(db))

    return chartObj.render()  # 그래프 정보 넘기기


def export_doy(ori_db):
    df = dp.load_final_data(ori_db['knps'], ori_db['class_num'])
    df_sos = pd.read_csv(root + f"{middle}data{middle}knps_sos.csv")
    df_sos = df_sos[['year', ori_db['knps'] + '_' + ori_db['class_num']]]
    df_sos.columns = ['year', 'sos']

    phenophase_date = ''
    phenophase_betw = ''

    sos = []
    doy = []
    betwn = []

    # sos 기준으로 개엽일 추출
    if ori_db['curve_fit'] == '1':
        # df, df_sos = pk.curve_fit(df, ori_db)
        # df_sos.columns = ['year', 'sos']
        df_sos = pd.read_csv(f"{root}{middle}data{middle}knps_sos.csv")

        for year in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):
            # phenophase_doy = df_sos[df_sos['year'] == year]['sos'].to_list()[0]  # sos 스칼라 값
            phenophase_doy = df_sos[f"{ori_db['knps']}_{ori_db['class_num']}"].iloc[year - 2003]
            phenophase_date = (f'{year}년 : {phenophase_doy}일')
            sos.append(phenophase_date)

    else:
        df, df_sos = pk.curve_fit(df, ori_db)

    for year in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):
        data = df[df['date'].str[:4] == str(year)]
        thresh = np.min(data['avg']) + ((np.max(data['avg']) - np.min(data['avg'])) * (
            float(ori_db["threshold"])))  ##개엽일의 EVI 값

        ## 개엽일 사이값 찾기
        high = data[data['avg'] >= thresh]['date'].iloc[0]
        low = data.date[[data[data['avg'] >= thresh].index[0] - 8]].to_list()[0]
        high_value = data.avg[data['date'] == high].to_list()[0]  ## high avg 값만 추출
        low_value = data.avg[data['date'] == low].to_list()[0]  ## low avg 값만 추출
        div_add = (high_value - low_value) / 8

        for a in range(8):
            if low_value > thresh:
                break
            else:
                low_value += div_add

        phenophase_doy = format(pd.to_datetime(low) + datetime.timedelta(days=a - 1), '%Y-%m-%d')
        phenophase_date = format(datetime.datetime.strptime(phenophase_doy, '%Y-%m-%d'), '%j') + '일,' + phenophase_doy
        phenophase_betw = (f'{low} ~ {high}')
        doy.append(phenophase_date)
        betwn.append(phenophase_betw)

    if ori_db['curve_fit'] == '1':
        total_DataFrame = pd.DataFrame(columns=['SOS기준 개엽일', '임계치 개엽일', '임계치 오차범위'])
        for i in range(len(doy)):
            total_DataFrame.loc[i] = [sos[i], doy[i], betwn[i]]
    else:
        total_DataFrame = pd.DataFrame(columns=['임계치 개엽일', '임계치 오차범위'])
        for i in range(len(doy)):
            total_DataFrame.loc[i] = [doy[i], betwn[i]]

    html_DataFrame = total_DataFrame.to_html(justify='center', index=False, table_id='mytable')

    return html_DataFrame


def open_model_processing(ori_db):
    with open(root + f"{middle}data{middle}model{middle}{ori_db['knps']}_{ori_db['class_num']}", 'r') as fin:
        m = model_from_json(fin.read())

    periods = 4
    for i in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):

        if i % 4 == 1:
            periods += 366

        else:
            periods += 365

    future = m.make_future_dataframe(periods)
    forecast = m.predict(future)

    df = forecast[['ds', 'yhat']]
    df.columns = ['date', 'avg']
    df['date'] = df['date'].astype('str')
    doy_list = []
    for i in range(len(df)):
        date = df.loc[i, 'date']
        calculate_doy = datetime.datetime(int(date[:4]), int(date[5:7]), int(date[8:10])).strftime("%j")
        doy_list.append(calculate_doy)

    df['DOY'] = doy_list

    # df, df_sos = phenoKOR.curve_fit(df, ori_db)

    df = df[(df['date'].str[:4] >= ori_db['start_year'])]

    df = df.reset_index(drop=True)

    return (df)


# 예측 모델 그래프 그리기
def get_predict_chart(ori_db):
    df = open_model_processing(ori_db)

    df = pd.read_csv(f"{root}{middle}data{middle}knps_final_predict.csv")
    df = df[(df["code"] == ori_db["knps"]) & (df["class"] == int(ori_db["class_num"])) &
            (df['date'].str[:4] >= ori_db["start_year"]) & (df['date'].str[:4] <= ori_db["end_year"])].sort_values(
        'date')

    data = []  # 그래프를 그리기 위한 데이터
    schema = [{"name": "Time", "type": "date", "format": "%Y-%m-%d"}, {"name": "EVI", "type": "number"}]
    print(df)
    for i in range(len(df)):  # data에 값 채우기
        data.append([df['date'].iloc[i], df['avg'].iloc[i]])

    fusionTable = FusionTable(json.dumps(schema), json.dumps(data))  # 데이터 테이블 만들기
    timeSeries = TimeSeries(fusionTable)  # 타임시리즈 만들기

    # 그래프 속성 설정하기
    timeSeries.AddAttribute('caption', f'{{"text":"EVI of {ori_db["knps"]}"}}')
    timeSeries.AddAttribute('chart',
                            f'{{"theme":"candy", "exportEnabled": "1", "exportfilename": "{ori_db["knps"]}_{ori_db["class_num"]}_{ori_db["start_year"]}_{ori_db["end_year"]}"}}')
    timeSeries.AddAttribute('subcaption', f'{{"text":"class_num : {ori_db["class_num"]}"}}')
    timeSeries.AddAttribute('yaxis', '[{"plot":{"value":"EVI"},"format":{"prefix":""},"title":"EVI"}]')

    # 그래프 그리기
    fcChart = FusionCharts("timeseries", "ex1", 960, 400, "chart-1", "json", timeSeries)

    # 그래프 정보 넘기기
    return fcChart.render()


def get_predict_multi_plot(ori_db):
    # curve fitting된 데이터 가져오기
    # df = open_model_processing(ori_db)

    df = pd.read_csv(f"{root}{middle}data{middle}knps_final_predict.csv")
    df = df[(df["code"] == ori_db["knps"]) & (df["class"] == int(ori_db["class_num"])) &
            (df['date'].str[:4] >= ori_db["start_year"]) & (df['date'].str[:4] <= ori_db["end_year"])].sort_values(
        'date')

    # 그래프 속성 및 데이터를 저장하는 변수
    db = {
        "chart": {  # 그래프 속성
            "exportEnabled": "1",
            "exportfilename": f"{ori_db['knps']}_{ori_db['class_num']}_{ori_db['start_year']}_{ori_db['end_year']}",
            "bgColor": "#262A33",
            "bgAlpha": "100",
            "showBorder": "0",
            "showvalues": "0",
            "numvisibleplot": "12",
            "caption": f"EVI of {ori_db['knps']}",
            "subcaption": f"class_num : {ori_db['class_num']}",
            "yaxisname": "EVI",
            "theme": "candy",
            "drawAnchors": "0",
            "plottooltext": "<b>$dataValue</b> EVI of $label",

        },
        "categories": [{  # X축
            "category": [{"label": str(i)} for i in range(1, 365)]
        }],
        "dataset": []  # Y축
    }

    # 데이터셋에 데이터 넣기
    for now in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):  # start_year에서 end_year까지
        db["dataset"].append({
            "seriesname": str(now),  # 레이블 이름
            # 해당 연도에 시작 (1월 1일)부터 (12월 31)일까지의 EVI 값을 넣기
            "data": [{"value": i} for i in
                     df[df['date'].str[:4] == str(now)].avg]
        })

    # 그래프 그리기
    chartObj = FusionCharts('scrollline2d', 'ex1', 960, 400, 'chart-1', 'json', json.dumps(db))

    return chartObj.render()  # 그래프 정보 넘기기


def predict_export_doy(ori_db):
    with open(root + f"{middle}data{middle}model{middle}{ori_db['knps']}_{ori_db['class_num']}", 'r') as fin:
        m = model_from_json(fin.read())

    periods = 0
    for i in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):
        if i % 4 == 0:
            periods += 370
        else:
            periods += 369

    future = m.make_future_dataframe(periods)
    forecast = m.predict(future)

    df = forecast[['ds', 'yhat']]
    df.columns = ['date', 'avg']
    df['date'] = df['date'].astype('str')
    doy_list = []
    for i in range(len(df)):
        date = df.loc[i, 'date']
        calculate_doy = datetime.datetime(int(date[:4]), int(date[5:7]), int(date[8:10])).strftime("%j")
        doy_list.append(calculate_doy)

    df['DOY'] = doy_list

    phenophase_date = ''
    phenophase_betw = ''

    sos = []
    doy = []
    betwn = []

    # sos 기준으로 개엽일 추출
    if ori_db['curve_fit'] == '1':
        # df, df_sos = pk.curve_fit(df, ori_db)
        # df_sos.columns = ['year', 'sos']
        df_sos = pd.read_csv(f"{root}{middle}data{middle}knps_final_predict_sos.csv")

        for year in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):
            # phenophase_doy = df_sos[df_sos['year'] == year]['sos'].to_list()[0]  # sos 스칼라 값
            phenophase_doy = df_sos[f"{ori_db['knps']}_{ori_db['class_num']}"].iloc[year - 2022]
            phenophase_date = (f'{year}년 : {phenophase_doy}일')
            sos.append(phenophase_date)

    else:
        df, df_sos = pk.curve_fit(df, ori_db)

    for year in range(int(ori_db['start_year']), int(ori_db['end_year']) + 1):
        data = df[df['date'].str[:4] == str(year)]
        thresh = np.min(data['avg']) + ((np.max(data['avg']) - np.min(data['avg'])) * (
            float(ori_db["threshold"])))  ##개엽일의 EVI 값

        ## 개엽일 사이값 찾기
        high = data[data['avg'] >= thresh]['date'].iloc[0]
        low = data.date[[data[data['avg'] >= thresh].index[0] - 8]].to_list()[0]
        high_value = data.avg[data['date'] == high].to_list()[0]  ## high avg 값만 추출
        low_value = data.avg[data['date'] == low].to_list()[0]  ## low avg 값만 추출
        div_add = (high_value - low_value) / 8

        for a in range(8):
            if low_value > thresh:
                break
            else:
                low_value += div_add

        phenophase_doy = format(pd.to_datetime(low) + datetime.timedelta(days=a - 1), '%Y-%m-%d')
        phenophase_date = format(datetime.datetime.strptime(phenophase_doy, '%Y-%m-%d'),
                                 '%j') + '일,' + phenophase_doy
        phenophase_betw = (f'{low} ~ {high}')
        doy.append(phenophase_date)
        betwn.append(phenophase_betw)

    if ori_db['curve_fit'] == '1':
        total_DataFrame = pd.DataFrame(columns=['SOS기준 개엽일', '임계치 개엽일', '임계치 오차범위'])
        for i in range(len(doy)):
            total_DataFrame.loc[i] = [sos[i], doy[i], betwn[i]]
    else:
        total_DataFrame = pd.DataFrame(columns=['임계치 개엽일', '임계치 오차범위'])
        for i in range(len(doy)):
            total_DataFrame.loc[i] = [doy[i], betwn[i]]

    html_DataFrame = total_DataFrame.to_html(justify='center', index=False, table_id='mytable')
    return html_DataFrame
