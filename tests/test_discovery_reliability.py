"""Regression tests for the September 2026 discovery-feed audit."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from test_update_jobs import monitor


class DiscoveryReliabilityTests(unittest.TestCase):
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    feed = dict(id='test-feed', name='Feed', url='https://www.indgovtjobs.in/',
                maxHeadlines=40, maxNewPerRun=1, proxyFallback=True)
    org = dict(id='board', name='Example Board', department='Example Board',
               aliases=['example'], url='https://example.gov.in/jobs',
               enrichDetails=False, type='central', noticeTypes=['recruitment'])
    headline = monitor.Candidate('Example Clerk Recruitment 2026',
                                 'https://www.indgovtjobs.in/2026/09/example-clerk.html')
    notice = monitor.Candidate('Example Clerk Recruitment 2026',
                              'https://example.gov.in/clerk-20260922.pdf')

    def state(self, **extra):
        source = dict(initializedAt='2026-09-01T00:00:00Z', fingerprints=[], discoveryVersion=2)
        source.update(extra)
        return {'sources': {self.feed['id']: source}}

    def scan(self, state, headlines=None, official_error=False, orgs=None, feed=None, now=None):
        page = monitor.Download(self.org['url'], 'text/html',
            b'<a href="/clerk-20260922.pdf">Example Clerk Recruitment 2026</a>')
        with patch.object(monitor, 'load_discovery_feeds', return_value=[feed or self.feed]), \
             patch.object(monitor, 'fetch_source_listing', return_value=page), \
             patch.object(monitor, 'discovery_candidates', return_value=headlines if headlines is not None else [self.headline]), \
             patch.object(monitor, 'register_official_website_from_article'), \
             patch.object(monitor, 'fetch_url', side_effect=RuntimeError('temporary timeout') if official_error else None, return_value=page):
            return monitor.process_discovery_feeds([self.org] if orgs is None else orgs, state, now or self.now, dry_run=True)

    def test_indgovtjobs_is_discovery_only_and_configured(self):
        feed = next(f for f in monitor.load_discovery_feeds() if f['id']=='indgovtjobs')
        self.assertEqual(feed['url'], 'https://www.indgovtjobs.in/feeds/posts/default?alt=rss')
        self.assertTrue(feed['proxyFallback'])
        self.assertEqual(feed['bootstrapCount'], 8)
        self.assertTrue(monitor.is_discovery_host(feed['url']))
        self.assertFalse(monitor.looks_like_official_website(feed['url']))
        self.assertNotIn('indgovtjobs', monitor.strip_discovery_branding('IndGovtJobs.in Example Clerk Recruitment').lower())

    def test_loader_preserves_transport_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'feeds.json'
            entry = dict(self.feed, sslFallback=True, timeout=7, detailTimeout=9)
            path.write_text(json.dumps({'feeds':[entry]}))
            loaded = monitor.load_discovery_feeds(path)[0]
        for key in ('proxyFallback','sslFallback','timeout','detailTimeout'):
            self.assertEqual(loaded[key], entry[key])

    def test_filter_precedes_limit(self):
        state = self.state()
        nav = [monitor.Candidate('Contact us', f'https://www.indgovtjobs.in/nav/{i}') for i in range(60)]
        jobs, added, _ = self.scan(state, nav + [self.headline], feed=dict(self.feed,maxHeadlines=1))
        self.assertEqual(added, 1)
        self.assertEqual(jobs[0]['noticeUrl'], self.notice.url)

    def test_html_table_preserves_employer_post_not_deadline_as_publication(self):
        page = monitor.Download('https://www.speedjob.in/latest-job/', 'text/html', b'''
            <table><tr><td>ITBP</td><td>Head Constable (Motor Mechanic)</td>
            <td>27.10.2026</td><td><a href="/itbp-recruitment/">Click here</a></td></tr></table>''')
        candidates = monitor.discovery_candidates(page)
        self.assertEqual(len(candidates), 1)
        self.assertIn('ITBP', candidates[0].title)
        self.assertIn('Motor Mechanic', candidates[0].title)
        self.assertTrue(monitor.looks_like_discovery_headline(candidates[0]))
        self.assertEqual(candidates[0].notice_date, '')
        self.assertEqual(candidates[0].published_at, '')

    def test_navigation_only_feed_is_failure_not_healthy_baseline(self):
        state = {}
        nav = [monitor.Candidate(t,'https://www.indgovtjobs.in/category') for t in
               ('Government Jobs','Bank Jobs','Railway Jobs','Free Job Alert','Employment News')]
        self.scan(state, nav)
        self.assertEqual(state['sourceHealth'][self.feed['id']]['consecutiveFailures'],1)
        self.assertNotIn(self.feed['id'], state['sources'])

    def test_temporary_failure_is_retried_and_then_deduplicated(self):
        state = self.state()
        self.assertEqual(self.scan(state, official_error=True)[1], 0)
        source = state['sources'][self.feed['id']]
        self.assertNotIn(monitor.fingerprint(self.headline), source['fingerprints'])
        self.assertEqual(len(source['pending']), 1)
        self.assertEqual(self.scan(state, now=self.now+timedelta(hours=6))[1], 1)
        self.assertFalse(source['pending'])
        self.assertEqual(self.scan(state, now=self.now+timedelta(hours=12))[1], 0)

    def test_unmatched_organisation_remains_pending(self):
        state = self.state()
        self.scan(state, orgs=[])
        source = state['sources'][self.feed['id']]
        self.assertFalse(source['fingerprints'])
        self.assertIn('organisation', next(iter(source['pending'].values()))['lastError'])
        self.assertEqual(self.scan(state)[1],1)

    def test_retry_queue_does_not_starve_other_leads(self):
        state = self.state()
        unmatched = monitor.Candidate('Unknown Board Driver Recruitment', 'https://www.indgovtjobs.in/unknown')
        self.scan(state, [unmatched, self.headline])
        self.assertEqual(self.scan(state, [unmatched,self.headline], now=self.now+timedelta(hours=6))[1],1)
        self.assertEqual(len(state['sources'][self.feed['id']]['pending']),1)

    def test_legacy_failed_fingerprints_reconsidered_once(self):
        state = self.state(fingerprints=[monitor.fingerprint(self.headline)])
        del state['sources'][self.feed['id']]['discoveryVersion']
        self.assertEqual(self.scan(state)[1],1)
        self.assertEqual(self.scan(state)[1],0)

    def test_legacy_replay_does_not_duplicate_official_notice(self):
        state = self.state(fingerprints=[monitor.fingerprint(self.headline)])
        del state['sources'][self.feed['id']]['discoveryVersion']
        state['sources']['board'] = dict(initializedAt='2026-09-01T00:00:00Z',fingerprints=[monitor.fingerprint(self.notice)])
        self.assertEqual(self.scan(state)[1],0)
        self.assertFalse(state['sources'][self.feed['id']]['pending'])

    def test_new_feed_explicit_bootstrap_publishes_first_run(self):
        state = {}
        self.assertEqual(self.scan(state,feed=dict(self.feed,bootstrapCount=1))[1],1)

    def test_default_first_scan_still_baselines(self):
        state = {}
        self.assertEqual(self.scan(state)[1],0)
        self.assertIn(monitor.fingerprint(self.headline),state['sources'][self.feed['id']]['fingerprints'])

    def test_build_failure_is_not_consumed(self):
        state = self.state()
        with patch.object(monitor,'job_from_candidate',side_effect=RuntimeError('PDF unavailable')):
            self.scan(state)
        self.assertFalse(state['sources'][self.feed['id']]['fingerprints'])
        self.assertEqual(self.scan(state)[1],1)

    def test_archive_and_expired_jobs_are_not_replayed(self):
        for job in [dict(alertType='recruitment',lastDate='01-09-2026'),
                    dict(alertType='result',pdfLink='https://example.gov.in/20240101120000.pdf')]:
            state=self.state()
            with patch.object(monitor,'job_from_candidate',return_value=job):
                self.assertEqual(self.scan(state)[1],0)
            self.assertFalse(state['sources'][self.feed['id']]['pending'])

    def test_aggregator_links_never_publish(self):
        state = self.state()
        with patch.object(monitor,'job_from_candidate',return_value={'pdfLink':'https://www.indgovtjobs.in/notice.pdf'}):
            self.assertEqual(self.scan(state)[1],0)
        self.assertFalse(state['sources'][self.feed['id']]['fingerprints'])

    def test_missing_board_aliases_now_match_approved_organisations(self):
        orgs = monitor.approved_official_organizations([])
        for name in ('NTPC Assistant Officer','CPRI MTS','ICMR-BMHRC Group B',
                     'Assam Rifles Technical Tradesman','Indian Army TGC-145',
                     'ITBP Head Constable','CSIR-NGRI Technician','UIICL Administrative Officer'):
            with self.subTest(name=name):
                self.assertIsNotNone(monitor.match_official_organization(name, orgs))

    def test_cookie_privacy_and_guides_are_not_notification_documents(self):
        for filename in ('CookiePolicy_v1.4.pdf','PrivacyPolicy.pdf','howtoapply.pdf','how-to-apply.pdf'):
            self.assertTrue(monitor.is_non_notice_document('https://example.gov.in/assets/'+filename))
        self.assertFalse(monitor.is_non_notice_document('https://example.gov.in/Advertisement-2026.pdf'))

    def test_application_page_does_not_pick_cookie_or_how_to_apply_pdf(self):
        candidate=monitor.Candidate('Example Clerk Recruitment', 'https://example.gov.in/clerk/apply')
        page=monitor.Download(candidate.url,'text/html',b'<a href="/assets/CookiePolicy_v1.pdf">Cookie Policy</a><a href="/assets/howtoapply.pdf">How to Apply</a>')
        with patch.object(monitor,'fetch_url',return_value=page):
            job=monitor.job_from_candidate(candidate,dict(self.org,enrichDetails=True),self.now)
        self.assertEqual(job['pdfLink'],candidate.url)
        self.assertEqual(job['applyLink'],candidate.url)

    def test_pending_leads_appear_in_health_summary(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('health_audit',Path(monitor.__file__).with_name('source_health_summary.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        state=self.state();self.scan(state,orgs=[])
        report=module.build_report(state,{'jobs':[]})
        self.assertIn('Unresolved discovery leads',report)
        self.assertIn(self.headline.title,report)

    def test_workflow_reports_health_even_after_failure(self):
        text=(Path(monitor.ROOT)/'.github/workflows/update-job-alerts.yml').read_text()
        self.assertIn('if: always()\n        run: python scripts/source_health_summary.py',text)

    def test_rss_entries_are_parsed_as_leads_not_article_body_links(self):
        page=monitor.Download('https://www.indgovtjobs.in/feeds/posts/default?alt=rss', 'application/rss+xml', b'''<?xml version="1.0"?><rss version="2.0"><channel><title>IndGovtJobs</title><item><title>Example Clerk Recruitment 2026</title><link>https://www.indgovtjobs.in/2026/09/example.html</link><description>&lt;a href="https://example.gov.in"&gt;Official Website&lt;/a&gt;</description><pubDate>Tue, 22 Sep 2026 05:25:05 +0000</pubDate></item></channel></rss>''')
        candidates=monitor.discovery_candidates(page)
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0].url,'https://www.indgovtjobs.in/2026/09/example.html')
        self.assertTrue(monitor.looks_like_discovery_headline(candidates[0]))

    def test_advertisement_number_is_not_a_vacancy_count(self):
        self.assertEqual(monitor.infer_vacancies('CRPD/SCO/2026-27/15 Posts'), 'See Notification')
        self.assertEqual(monitor.infer_vacancies('CRPD/SCO/2026-27/20 Posts'), 'See Notification')
        self.assertEqual(monitor.infer_vacancies('35 Posts'), '35 Posts')

    def test_major_central_sources_are_enabled_with_fallback(self):
        sources=json.loads((monitor.ROOT/'automation/sources.json').read_text())['sources']
        for source in sources:
            if source['id'] in {'ssc','upsc','nvs','nvs-admission-updates'}:
                self.assertTrue(source['enabled'])
                self.assertTrue(source['proxyFallback'])
