#!/usr/bin/env bash
# Один прогін стабільності: k6 normal + семплінг CPU/RAM застосунку.
# $1 = назва прогону, $2 = cpus-квота для застосунку (напр. 0.25, або "none"), $3 = noise (yes/no)
set -u
NAME=$1; CPUS=$2; NOISE=$3; PROFILE=${4:-normal}
W=/home/claude/work; OUT=$W/expS/$NAME; mkdir -p $OUT
APP_PID=$(pgrep -f "^/home/claude/work/venv313/bin/python app.py" | head -1)
CG=/sys/fs/cgroup/cpu/lab5app
# guard: жодного залишкового шуму + cool-down, щоб прогони не впливали один на одного
pkill -x xz 2>/dev/null
sleep 15
if [ "$CPUS" != "none" ]; then
  echo $(python3 -c "print(int($CPUS*100000))") > $CG/cpu.cfs_quota_us   # те саме, що docker --cpus=$CPUS
else
  echo -1 > $CG/cpu.cfs_quota_us
fi
echo $APP_PID > $CG/cgroup.procs
for t in $(ls /proc/$APP_PID/task); do echo $t > $CG/tasks 2>/dev/null; done
NPIDS=""
if [ "$NOISE" != "no" ]; then
  N=2; [ "$NOISE" = "heavy" ] && N=4
  # сторонній процес: важка компресія логів на всіх ядрах
  for i in $(seq 1 $N); do ( while true; do xz -9e -T1 -c $W/expS/fake_app.log > /dev/null; done ) & NPIDS="$NPIDS $!"; done
fi
# семплінг ресурсів застосунку раз на секунду
( while true; do ps -o %cpu=,rss= -p $APP_PID; echo "LOAD $(cut -d' ' -f1 /proc/loadavg)"; sleep 1; done ) > $OUT/resources.txt & SPID=$!
ST0=$(awk '/^cpu /{print $9}' /proc/stat)
k6 run -q -e PROFILE=$PROFILE -e BASE_URL=http://localhost:5000 \
   --summary-export $OUT/summary.json "/home/claude/repo/Curs_Project/last – копія/load/balance.js" > $OUT/k6.txt 2>&1
RC=$?; ST1=$(awk '/^cpu /{print $9}' /proc/stat)
echo "steal_ticks $((ST1-ST0))" >> $OUT/k6.txt
echo "k6 exit code: $RC" >> $OUT/k6.txt
kill $SPID 2>/dev/null
for p in $NPIDS; do kill $p 2>/dev/null; done   # спершу цикли, потім самі xz
sleep 0.5; pkill -x xz 2>/dev/null
echo -1 > $CG/cpu.cfs_quota_us
tail -1 $OUT/k6.txt
