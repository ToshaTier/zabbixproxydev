#!/bin/bash 
proxyIP=$1
proxyPORT=$2
serverHost=$3
item=$4
value=$5
msg='ZSMSG,00000,{"Server" : "zabbixvm.ath","Items" : [{"host" : "'$serverHost'","item" : "'$item'","value" : "'$value'"}]}'
echo -n $msg | nc -w1 -4u $proxyIP $proxyPORT
