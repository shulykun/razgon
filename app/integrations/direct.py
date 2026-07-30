"""Yandex Direct API integration."""
import requests
import json
import logging

logger = logging.getLogger(__name__)

DIRECT_API = "https://api.direct.yandex.com/json/v5"
SANDBOX_API = "https://api-sandbox.direct.yandex.com/json/v5"

class DirectClient:
    def __init__(self, token, client_login=None, sandbox=False):
        self.token = token
        self.client_login = client_login
        self.base_url = SANDBOX_API if sandbox else DIRECT_API

    def _headers(self):
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        }
        if self.client_login:
            h["Client-Login"] = self.client_login
        return h

    def _call(self, service, method, params=None):
        url = f"{self.base_url}/{service}"
        body = {"method": method}
        if params:
            body["params"] = params
        resp = requests.post(url, headers=self._headers(), json=body, timeout=60)
        # Reports API returns TSV
        if service == "reports":
            if resp.status_code == 200:
                return self._parse_tsv(resp.text)
            try:
                data = resp.json()
                if "error" in data:
                    err = data["error"]
                    return {"error": f"{err.get('error_code')}: {err.get('error_detail', err.get('error_string'))}"}
                return data.get("result", data)
            except Exception:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}
        data = resp.json()
        if "error" in data:
            err = data["error"]
            logger.error(f"Direct API error: {err.get('error_code')} - {err.get('error_detail', err.get('error_string'))}")
            return {"error": f"{err.get('error_code')}: {err.get('error_detail', err.get('error_string'))}"}
        return data.get("result", data)

    @staticmethod
    def _parse_tsv(text):
        """Parse TSV report into structured JSON."""
        lines = [l for l in text.strip().split("\n") if l and not l.startswith('"')]
        if len(lines) < 2:
            return {"rows": [], "total_rows": 0}
        headers = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            vals = line.split("\t")
            row = {}
            for i, h in enumerate(headers):
                val = vals[i] if i < len(vals) else ""
                # Try to convert numbers
                try:
                    if "." in val:
                        val = float(val)
                    else:
                        val = int(val)
                except (ValueError, TypeError):
                    pass
                row[h] = val
            rows.append(row)
        # Summary row (last)
        summary = None
        if rows and len(rows[-1]) == len(headers):
            last = rows[-1]
            first_val = str(list(last.values())[0])
            if "Total" in first_val or "total" in first_val:
                summary = rows.pop()
        return {"headers": headers, "rows": rows, "total_rows": len(rows), "summary": summary}

    # ── Campaigns ──
    def get_campaigns(self, field_names=None):
        """Get all campaigns."""
        params = {
            "SelectionCriteria": {"States": ["ON", "SUSPENDED", "OFF"]},
            "FieldNames": field_names or ["Id", "Name", "State", "Status", "StartDate", "EndDate",
                                          "DailyBudget", "Statistics", "Type", "Funds"],
        }
        return self._call("campaigns", "get", params)

    def get_campaign_stats(self, campaign_ids, date_from=None, date_to=None):
        """Get campaign statistics."""
        from datetime import datetime, timedelta
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        params = {
            "SelectionCriteria": {
                "DateFrom": date_from,
                "DateTo": date_to,
            },
            "FieldNames": ["Impressions", "Clicks", "Cost", "Ctr", "CampaignId", "CampaignName"],
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "ReportName": f"campaign_stats_{date_from}_{date_to}",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
        return self._call("reports", "get", params)

    def suspend_campaign(self, campaign_id):
        return self._call("campaigns", "suspend", {"SelectionCriteria": {"Ids": [campaign_id]}})

    def resume_campaign(self, campaign_id):
        return self._call("campaigns", "resume", {"SelectionCriteria": {"Ids": [campaign_id]}})

    # ── Ad Groups ──
    def get_ad_groups(self, campaign_ids=None):
        params = {
            "FieldNames": ["Id", "Name", "CampaignId", "Status", "Type", "RegionIds"],
        }
        if campaign_ids:
            params["SelectionCriteria"] = {"CampaignIds": campaign_ids}
        return self._call("adgroups", "get", params)

    # ── Ads ──
    def get_ads(self, campaign_ids=None, ad_ids=None):
        params = {
            "FieldNames": ["Id", "AdGroupId", "CampaignId", "State", "Status", "Type"],
            "TextAdFieldNames": ["Title", "Text", "Href"],
        }
        criteria = {}
        if campaign_ids:
            criteria["CampaignIds"] = campaign_ids
        if ad_ids:
            criteria["Ids"] = ad_ids
        if criteria:
            params["SelectionCriteria"] = criteria
        return self._call("ads", "get", params)

    # ── Keywords ──
    def get_keywords(self, campaign_ids=None, ad_group_ids=None):
        params = {
            "FieldNames": ["Id", "Keyword", "AdGroupId", "CampaignId", "Bid", "Status"],
        }
        criteria = {}
        if campaign_ids:
            criteria["CampaignIds"] = campaign_ids
        if ad_group_ids:
            criteria["AdGroupIds"] = ad_group_ids
        if criteria:
            params["SelectionCriteria"] = criteria
        return self._call("keywords", "get", params)

    def set_keyword_bids(self, keyword_bids):
        """Set bids. keyword_bids = [{"KeywordId": int, "Bid": int}, ...]"""
        return self._call("bids", "set", {"Bids": keyword_bids})

    # ── Search queries (report) ──
    def get_search_queries(self, campaign_ids, date_from=None, date_to=None):
        """Get actual search queries that triggered ads."""
        from datetime import datetime, timedelta
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        params = {
            "SelectionCriteria": {
                "Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(c) for c in campaign_ids]}],
                "DateFrom": date_from,
                "DateTo": date_to,
            },
            "FieldNames": ["Query", "Impressions", "Clicks", "Cost", "Ctr"],
            "ReportType": "SEARCH_QUERY_PERFORMANCE_REPORT",
            "ReportName": f"search_queries_{date_from}_{date_to}",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
        return self._call("reports", "get", params)

    # ── Negative keywords ──
    def add_negative_keywords(self, ad_group_id, keywords):
        """Add negative keywords to an ad group."""
        return self._call("negativekeywordsets", "add", {
            "NegativeKeywordSets": [{
                "AdGroupId": ad_group_id,
                "NegativeKeywords": {"Items": keywords},
            }]
        })

    # ── Conversion report ──
    def get_conversions(self, campaign_ids, date_from=None, date_to=None):
        """Get conversions by campaign from Direct reports."""
        from datetime import datetime, timedelta
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        params = {
            "SelectionCriteria": {
                "Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(c) for c in campaign_ids]}],
                "DateFrom": date_from,
                "DateTo": date_to,
            },
            "FieldNames": [
                "CampaignId", "CampaignName", "Impressions", "Clicks", "Cost", "Ctr",
                "Conversions", "ConversionRate", "CostPerConversion",
                "GoalsRoi", "Revenue", "Profit",
                "BounceRate", "AvgPageviews",
            ],
            "ReportType": "CUSTOM_REPORT",
            "ReportName": f"conversions_{date_from}_{date_to}",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
        return self._call("reports", "get", params)

    # ── Placement report ──
    def get_placements(self, campaign_ids, date_from=None, date_to=None):
        """Get performance by placement (site/app) in RSYA."""
        from datetime import datetime, timedelta
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        params = {
            "SelectionCriteria": {
                "Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(c) for c in campaign_ids]}],
                "DateFrom": date_from,
                "DateTo": date_to,
            },
            "FieldNames": ["Placement", "Impressions", "Clicks", "Cost", "Ctr"],
            "ReportType": "CUSTOM_REPORT",
            "ReportName": f"placements_{date_from}_{date_to}",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
        return self._call("reports", "get", params)

    # ── Search query spam check ──
    def check_query_spam(self, campaign_ids, date_from=None, date_to=None, min_impressions=3):
        """Find search queries that waste budget (impressions but 0 clicks)."""
        report = self.get_search_queries(campaign_ids, date_from, date_to)
        if "error" in report:
            return report
        waste = [r for r in report["rows"] if int(r.get("Clicks", 0)) == 0 and int(r.get("Impressions", 0)) >= min_impressions]
        waste.sort(key=lambda x: int(x.get("Impressions", 0)), reverse=True)
        return {"waste_queries": waste, "total_waste": len(waste)}

    # ── Summary helper ──
    def get_account_summary(self):
        """Quick overview: campaigns, budget, stats."""
        campaigns = self.get_campaigns()
        if "error" in campaigns:
            return campaigns
        result = {"campaigns": []}
        for c in campaigns.get("Campaigns", []):
            info = {
                "id": c.get("Id"),
                "name": c.get("Name"),
                "state": c.get("State"),
                "status": c.get("Status"),
                "daily_budget": c.get("DailyBudget", {}),
            }
            stats = c.get("Statistics", {})
            if stats:
                info["impressions"] = stats.get("ImpressionsSearch") or stats.get("Impressions")
                info["clicks"] = stats.get("ClicksSearch") or stats.get("Clicks")
                info["cost"] = stats.get("CostSearch") or stats.get("Cost")
            result["campaigns"].append(info)
        return result
