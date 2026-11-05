#!/bin/bash
# Moves the live strategies off this Mac: stops the Mac schedules and Terminal loops, then bundles their data
# for GitHub. Nothing is deleted: schedule files move to ~/paper_jobs/old_launchagents, data is copied.
set -u; O="$HOME/paper_jobs/cutover"; mkdir -p "$O" "$HOME/paper_jobs/old_launchagents"; T=$(mktemp -d)
for L in com.pat.paperfund com.pat.portablealpha com.pat.forwardtest com.pat.bili.entry com.pat.bili.exit; do
  P="$HOME/Library/LaunchAgents/$L.plist"
  if [ -f "$P" ]; then launchctl unload "$P" 2>/dev/null; mv "$P" "$HOME/paper_jobs/old_launchagents/"; echo "stopped schedule $L"; fi
done
pkill -f paper_maker.py && echo "stopped Kalshi paper maker"; pkill -f hl_logger.py && echo "stopped Hyperliquid logger"; sleep 2
# funds
mkdir -p "$T/funds"; F="$HOME/paper_jobs"
cp "$F/paper_fund/fund_log.csv" "$F/paper_fund/fund_log_v1_dry.csv" "$T/funds/" 2>/dev/null; cp "$F/paper_fund/last_run.txt" "$T/funds/last_run_fund.txt" 2>/dev/null
cp "$F/portable_alpha/pa_log.csv" "$F/portable_alpha/pa_log_dry.csv" "$T/funds/" 2>/dev/null; cp "$F/portable_alpha/last_run.txt" "$T/funds/last_run_pa.txt" 2>/dev/null
cp "$F"/bili/*.csv "$T/funds/" 2>/dev/null
# kalshi maker
K="$HOME/Desktop/research_lab"; mkdir -p "$T/kalshi/paper_maker" "$T/kalshi/reports"
cp "$K"/paper_maker/* "$T/kalshi/paper_maker/"; cp "$K/reports/paper_maker_summary.txt" "$T/kalshi/reports/" 2>/dev/null
# hyperliquid logger
H="$HOME/Desktop/hl_research/live"; mkdir -p "$T/hl"; cp -R "$H/wallets.json" "$H/coin_hourly.csv" "$H/logger_log.txt" "$H/raw" "$T/hl/"
# forward test
W="$HOME/Desktop/forward_test"; mkdir -p "$T/fwd"; cp -R "$W/hourly" "$W/metrics" "$W/signal_cache.json" "$W/summary.txt" "$W/trades.csv" "$W/fwd_log.txt" "$T/fwd/"
for d in funds kalshi hl fwd; do tar -czf "$O/$d.tar.gz" -C "$T/$d" . && echo "bundled $d ($(du -h "$O/$d.tar.gz" | cut -f1))"; done
rm -rf "$T"; echo "Done. Tell Claude the cutover finished. You can close this window."
