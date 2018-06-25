#!/bin/bash 
proxyIP=$1
proxyPORT=$2
serverHost=$3
msgRate=$4
item=$5
pause=`echo "(1/$msgRate)" | bc -l`
echo "Pause is: $pause"
echo "started at $(date +%s)"
for i in $(seq 1 $msgRate)
do  
    msg='ZSMSG,00000,{"Server" : "zabbixvm.ath","Items" : [{"host" : "'$serverHost'","item" : "'$item'","value" : "'$i'"}]}'
    echo "$msg"
    echo "$msg" > /dev/udp/$proxyIP/$proxyPORT
    sleep $pause
done
echo "finished at $(date +%s)"
#echo -n $msg | nc -w1 -4u $proxyIP $proxyPORT
