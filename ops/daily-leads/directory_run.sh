#!/bin/zsh
# One directory scout (Y Combinator / Product Hunt pages, platform "web") per workspace that has directory tasks.
cd "$(dirname "$0")"
LOG=logs/$(date +%Y-%m-%d)-directory-scout.log
for org in "Shubhangi freelance" "Finance SaaS" "Leadnius GTM Lab"; do
  have=$(python3 -c "import daily_leads as d; d.TOTAL_MODE=True; print(d.leads_today('$org'))")
  [ "$have" -ge 30 ] && { echo "=== $org skipped ($have/30)" >> $LOG; continue; }
  echo "=== $org $(date +%H:%M) ($have/30)" >> $LOG
  python3 run_scout.py "$org" 15 $((30 - have)) web >> $LOG 2>&1
  echo "=== $org now $(python3 -c "import daily_leads as d; d.TOTAL_MODE=True; print(d.leads_today('$org'))")/30 $(date +%H:%M)" >> $LOG
done
echo "=== ALL DONE $(date +%H:%M)" >> $LOG
