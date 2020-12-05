#!/usr/bin/env python3

import requests
import time
from prometheus_client import Gauge, start_http_server
import subprocess
from datetime import datetime


USERNAME = "admin"
PASSWORD = "password"
MODEM_ADDRESS = "192.168.100.1"


r = requests.Session()

docsis_snr = Gauge('docsis_snr', 'Docsis SNR', ['channel', 'direction'])
docsis_power = Gauge('docsis_power', 'Docsis channel power', ['channel', 'direction'])
docsis_frequency = Gauge('docsis_frequency', 'Docsis frequency', ['channel', 'direction'])
docsis_correctable = Gauge('docsis_correctable', 'Docsis correctable', ['channel', 'direction'])
docsis_uncorrectable = Gauge('docsis_uncorrectable', 'Docsis uncorrectable', ['channel', 'direction'])
docsis_channel_id = Gauge('docsis_channel_id', 'Docsis channel id', ['channel', 'direction'])
docsis_symbol_rate = Gauge('docsis_symbol_rate', 'Docsis symbol rate', ['channel', 'direction'])

ping_min = Gauge("ping_min", 'ping min', ["target", "mode"])
ping_avg = Gauge("ping_avg", 'ping avg', ["target", "mode"])
ping_max = Gauge("ping_max", 'ping max', ["target", "mode"])
ping_mdev = Gauge("ping_mdev", 'ping mdev', ["target", "mode"])
ping_loss = Gauge("ping_loss", "ping loss", ["target", "mode"])


def ping(target, mode="4"):
    """PING a.fi (193.166.4.1) 56(84) bytes of data.
    --- a.fi ping statistics ---
    10 packets transmitted, 10 received, 0% packet loss, time 8996ms
    rtt min/avg/max/mdev = 17.395/23.978/34.866/5.381 ms"""
    p = subprocess.Popen(["ping", "-q", "-c", "10", "-%s" % mode, target], stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    for row in stdout.decode("utf-8").splitlines():
        if "packet loss" in row:
            loss = int(row.split()[5][:-1].strip())
            ping_loss.labels(target=target, mode=mode).set(loss)
        elif 'min/avg/max/mdev' in row:
            min_rtt,avg_rtt,max_rtt,mdev_rtt = [float(x) for x in row.split()[3].split("/")]
            ping_min.labels(target=target, mode=mode).set(min_rtt)
            ping_avg.labels(target=target, mode=mode).set(avg_rtt)
            ping_max.labels(target=target, mode=mode).set(max_rtt)
            ping_mdev.labels(target=target, mode=mode).set(mdev_rtt)


def login():
    sessionKey = None
    # Get session key
    print("Logging in")
    try:
        req = r.get("http://{}/".format(MODEM_ADDRESS), timeout=30)
    except Exception as exc:
        print("ERROR")
        print(exc)
        return
    for row in req.text.splitlines():
        if row.startswith("var SessionKey ="):
            sessionKey = row.split("=")[1].strip()

    # Do login
    req = r.post("http://{}/goform/login?sessionKey={}".format(MODEM_ADDRESS, sessionKey), data={"loginOrInitDS": "0", "loginUsername": USERNAME, "loginPassword": PASSWORD}, timeout=30)
    req.close()
    print("logged in")


def get_docsis_stats():
    # Get stats
    try:
        req = r.get("http://{}/RgConnect.asp".format(MODEM_ADDRESS), timeout=30)
    except Exception as exc:
        print("ERROR")
        print(exc)
        return
    if req.status_code != 200 or 'Residential Gateway Login' in req.text:
        # Because why to use correct status code?
        login()
        req = r.get("http://{}/RgConnect.asp".format(MODEM_ADDRESS), timeout=30)
        if req.status_code != 200:
            print("Failed to get stats")
    downstream_channels = []
    upstream_channels = []
    for row in req.text.splitlines():
        if 'QAM256' in row:
            parts = row.replace("<td>", "").replace("</td>", ",").replace("</tr>", "").replace("<tr bgcolor=\"#9999CC\">", "").replace("<tr bgcolor=\"#99CCFF\">", "").replace("Hz", "").replace("dBmV", "").replace("dB", "").split(",")
            downstream_channels.append(dict(zip(["channel", "lock", "modulation", "channel_id", "frequency", "power", "snr", "correctables", "uncorrectables"], [x.strip() for x in parts])))
        if  'ATDMA' in row:
            parts = row.replace("<td>", "").replace("</td>", ",").replace("</tr>", "").replace("<tr bgcolor=\"#9999CC\">", "").replace("<tr bgcolor=\"#99CCFF\">", "").replace("Hz", "").replace("dBmV", "").replace("dB", "").replace("Ksym/sec", "").split(",")
            upstream_channels.append(dict(zip(["channel", "lock", "modulation", "channel_id","symbol_rate", "frequency", "power"], [x.strip() for x in parts])))

    for channel in downstream_channels:
        docsis_power.labels(channel=int(channel['channel']), direction='downstream').set(float(channel['power']))
        docsis_snr.labels(channel=int(channel['channel']), direction='downstream').set(float(channel['snr']))
        docsis_frequency.labels(channel=int(channel['channel']), direction='downstream').set(int(channel['frequency']))
        docsis_correctable.labels(channel=int(channel['channel']), direction='downstream').set(int(channel['correctables']))
        docsis_uncorrectable.labels(channel=int(channel['channel']), direction='downstream').set(int(channel['uncorrectables']))
        docsis_channel_id.labels(channel=int(channel['channel']), direction='downstream').set(int(channel['channel_id']))

    for channel in upstream_channels:
        docsis_power.labels(channel=int(channel['channel']), direction='upstream').set(float(channel['power']))
        docsis_symbol_rate.labels(channel=int(channel['channel']), direction='upstream').set(int(channel['symbol_rate']))
        docsis_frequency.labels(channel=int(channel['channel']), direction='upstream').set(int(channel['frequency']))
        docsis_channel_id.labels(channel=int(channel['channel']), direction='upstream').set(int(channel['channel_id']))
    print("%s: got statistics" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == '__main__':
    start_http_server(8009)
    while True:
        get_docsis_stats()
        time.sleep(59)

