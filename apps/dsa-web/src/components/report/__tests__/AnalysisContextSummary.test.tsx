import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import type {
  AnalysisContextPackOverview,
  AnalysisReport,
  AnalysisResult,
  MarketStructureContext,
} from '../../../types/analysis';
import { AnalysisContextSummary } from '../AnalysisContextSummary';
import { ReportSummary } from '../ReportSummary';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getDiagnostics: vi.fn(),
    getNews: vi.fn(),
  },
}));

const overview: AnalysisContextPackOverview = {
  packVersion: '1.0',
  createdAt: '2026-04-10T08:30:00+00:00',
  subject: {
    code: '600519',
    stockName: '贵州茅台',
    market: 'cn',
  },
  blocks: [
    {
      key: 'quote',
      label: '行情',
      status: 'available',
      source: 'mock_quote',
      warnings: [],
      missingReasons: [],
    },
    {
      key: 'news',
      label: '新闻',
      status: 'missing',
      source: null,
      warnings: ['news_provider_timeout'],
      missingReasons: ['news_context_missing'],
    },
    {
      key: 'fundamentals',
      label: '基本面',
      status: 'fetch_failed',
      source: 'fundamental_pipeline',
      warnings: [],
      missingReasons: ['fundamental_pipeline_failed'],
    },
  ],
  counts: {
    available: 1,
    missing: 1,
    notSupported: 0,
    fallback: 0,
    stale: 0,
    estimated: 0,
    partial: 0,
    fetchFailed: 1,
  },
  dataQuality: {
    overallScore: 82,
    level: 'usable',
    blockScores: {
      quote: 100,
      daily_bars: 100,
      technical: 100,
      news: 35,
      fundamentals: 25,
      chip: 100,
    },
    limitations: ['fundamentals: fetch_failed'],
  },
  warnings: ['intraday_realtime_overlay'],
  metadata: {
    triggerSource: 'api',
    newsResultCount: 3,
  },
};

const marketStructure: MarketStructureContext = {
  schemaVersion: 'market-structure-v1',
  status: 'ok',
  market: 'cn',
  tradeDate: '2026-07-12',
  marketThemeContext: {
    schemaVersion: 'market-theme-v1',
    status: 'ok',
    market: 'cn',
    activeThemes: [{ name: 'Robotics', rank: 1, source: 'concept' }],
    leadingConcepts: [],
    leadingIndustries: [],
    laggingThemes: [],
    themeBreadth: {
      activeCount: 1,
      leadingConceptCount: 0,
      leadingIndustryCount: 0,
      laggingCount: 0,
    },
    dataQuality: { status: 'ok', missingFields: [], sources: [], errors: [] },
  },
  stockMarketPosition: {
    schemaVersion: 'stock-market-position-v1',
    status: 'ok',
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    market: 'cn',
    primaryTheme: { name: 'Robotics', source: 'concept', rank: 1 },
    relatedBoards: [],
    stockRole: 'follower',
    themePhase: 'accelerating',
    riskTags: [],
    missingFields: [],
  },
};

describe('AnalysisContextSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a collapsed summary and expands overview details on demand', () => {
    render(<AnalysisContextSummary overview={overview} />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(within(panel).getAllByText('Input Blocks')[0]).toBeVisible();
    expect(screen.getAllByText('Available 1')[0]).toBeVisible();
    expect(screen.getAllByText('Missing 1')[0]).toBeVisible();
    expect(screen.getAllByText('Fetch failed 1')[0]).toBeVisible();
    expect(screen.getAllByText('Quality 82/100 Usable')[0]).toBeVisible();
    expect(screen.getByText('Trigger: api')).toBeVisible();
    expect(screen.getByText('Source: mock_quote')).not.toBeVisible();

    fireEvent.click(within(panel).getAllByText('Input Blocks')[0]);

    expect(panel).toHaveAttribute('open');
    expect(screen.getByText('行情')).toBeInTheDocument();
    expect(screen.getByText('Source: mock_quote')).toBeVisible();
    expect(screen.getByText('Warnings:')).toBeInTheDocument();
    expect(screen.getByText(/intraday_realtime_overlay/)).toBeInTheDocument();
    expect(screen.getByText('Data Limitations:')).toBeInTheDocument();
    expect(screen.getByText(/fundamentals: Fetch failed/)).toBeInTheDocument();
    expect(screen.getByText(/news_provider_timeout/)).toBeInTheDocument();
    expect(screen.getByText(/Details: News was not included in this LLM run, so the conclusion did not use news context/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnostic code: news_context_missing/)).toBeInTheDocument();
    expect(screen.getByText(/related news on the report page is loaded separately and does not indicate that it was used in this analysis/)).toBeInTheDocument();
    expect(screen.getByText('Source: Input source not recorded')).toBeInTheDocument();
    expect(screen.queryByText(/^Action:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Scope:/)).not.toBeInTheDocument();
    const fundamentalsBlock = screen.getByText('基本面').closest('.home-subpanel');
    expect(fundamentalsBlock).not.toBeNull();
    const fundamentals = within(fundamentalsBlock as HTMLElement);
    expect(fundamentals.getByText(/Details: Fundamental retrieval failed and this analysis did not use fundamental data/)).toBeInTheDocument();
    expect(fundamentals.getByText(/Diagnostic code: fundamental_pipeline_failed/)).toBeInTheDocument();
    expect(screen.getAllByText('News Results: 3').some((item) => item.textContent === 'News Results: 3')).toBe(true);
    expect(screen.getAllByText('Analysis Input')[0]).toBeVisible();
  });

  it('localizes the collapsed summary for english reports', () => {
    render(<AnalysisContextSummary overview={overview} language="en" />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(screen.getAllByText('Input Blocks')[0]).toBeVisible();
    expect(screen.getByText('Shows inputs included in this LLM run, not provider run success')).toBeVisible();
    expect(screen.getAllByText('Available 1')[0]).toBeVisible();
    expect(screen.getAllByText('Missing 1')[0]).toBeVisible();
    expect(screen.getAllByText('Fetch failed 1')[0]).toBeVisible();
    expect(screen.getAllByText('Quality 82/100 Usable')[0]).toBeVisible();
    expect(screen.getByText('Trigger: api')).toBeVisible();

    fireEvent.click(within(panel).getAllByText('Input Blocks')[0]);

    expect(screen.getByText('Data Limitations:')).toBeInTheDocument();
    expect(screen.getByText(/fundamentals: Fetch failed/)).toBeInTheDocument();
    expect(screen.getByText(/Details: News was not included in this LLM run, so the conclusion did not use news context/)).toBeInTheDocument();
    expect(screen.getByText(/related news on the report page is loaded separately and does not indicate that it was used in this analysis/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnostic code: news_context_missing/)).toBeInTheDocument();
    expect(screen.queryByText(/^Action:/)).not.toBeInTheDocument();
  });

  it('does not claim available fundamentals were unused when only provenance is missing', () => {
    const availableFundamentalsOverview: AnalysisContextPackOverview = {
      ...overview,
      blocks: [{
        key: 'fundamentals',
        label: '基本面',
        status: 'available',
        source: null,
        warnings: [],
        missingReasons: ['fundamental_source_chain_missing'],
      }],
      counts: {
        available: 1,
        missing: 0,
        notSupported: 0,
        fallback: 0,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
    };

    render(<AnalysisContextSummary overview={availableFundamentalsOverview} />);

    fireEvent.click(screen.getAllByText('Input Blocks')[0]);

    expect(screen.getByText(/Details: Fundamental source-chain metadata was not recorded/)).toBeInTheDocument();
    expect(screen.getByText(/use the current status to determine whether fundamentals were included/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnostic code: fundamental_source_chain_missing/)).toBeInTheDocument();
    expect(screen.queryByText(/did not use fundamental data/)).not.toBeInTheDocument();
  });

  it('uses status guidance for unknown reason codes without adding another field', () => {
    const unknownReasonOverview: AnalysisContextPackOverview = {
      ...overview,
      blocks: [{
        key: 'fundamentals',
        label: '基本面',
        status: 'fetch_failed',
        source: 'fundamental_pipeline',
        warnings: [],
        missingReasons: ['brand_new_internal_code'],
      }],
      counts: {
        available: 0,
        missing: 0,
        notSupported: 0,
        fallback: 0,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 1,
      },
    };

    render(<AnalysisContextSummary overview={unknownReasonOverview} />);

    fireEvent.click(screen.getAllByText('Input Blocks')[0]);

    expect(screen.getByText(/Details: Data retrieval failed and this analysis did not use the data/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnostic code: brand_new_internal_code/)).toBeInTheDocument();
    expect(screen.queryByText(/^Action:/)).not.toBeInTheDocument();
  });

  it('explains the real chip_not_supported reason with actionable guidance', () => {
    const unsupportedChipOverview: AnalysisContextPackOverview = {
      ...overview,
      blocks: [{
        key: 'chip',
        label: '筹码',
        status: 'not_supported',
        source: null,
        warnings: [],
        missingReasons: ['chip_not_supported'],
      }],
      counts: {
        available: 0,
        missing: 0,
        notSupported: 1,
        fallback: 0,
        stale: 0,
        estimated: 0,
        partial: 0,
        fetchFailed: 0,
      },
    };

    render(<AnalysisContextSummary overview={unsupportedChipOverview} />);

    fireEvent.click(screen.getAllByText('Input Blocks')[0]);

    expect(screen.getByText(/Details: Chip data is not supported for this market or symbol and was not used/)).toBeInTheDocument();
    expect(screen.getByText(/Diagnostic code: chip_not_supported/)).toBeInTheDocument();
    expect(screen.queryByText(/^Action:/)).not.toBeInTheDocument();
  });

  it('surfaces degraded non-zero states in the collapsed summary', () => {
    const degradedOverview: AnalysisContextPackOverview = {
      ...overview,
      blocks: [
        {
          key: 'quote',
          label: '行情',
          status: 'fallback',
          source: 'cached_quote',
          warnings: ['quote_fallback'],
          missingReasons: [],
        },
        {
          key: 'fundamental',
          label: '基本面',
          status: 'stale',
          source: 'fundamental_cache',
          warnings: ['stale_fundamental'],
          missingReasons: [],
        },
        {
          key: 'technical',
          label: '技术',
          status: 'partial',
          source: 'technical_pipeline',
          warnings: ['technical_partial'],
          missingReasons: [],
        },
        {
          key: 'chip',
          label: '筹码',
          status: 'estimated',
          source: 'estimated_chip',
          warnings: [],
          missingReasons: [],
        },
        {
          key: 'daily_bars',
          label: '日线',
          status: 'not_supported',
          source: null,
          warnings: [],
          missingReasons: [],
        },
      ],
      counts: {
        available: 0,
        missing: 0,
        notSupported: 1,
        fallback: 1,
        stale: 1,
        estimated: 1,
        partial: 1,
        fetchFailed: 0,
      },
    };

    render(<AnalysisContextSummary overview={degradedOverview} />);

    const panel = screen.getByTestId('analysis-context-summary');
    expect(panel).not.toHaveAttribute('open');
    expect(within(panel).getByText('Available 0')).toBeVisible();
    expect(within(panel).getByText('Missing 0')).toBeVisible();
    expect(within(panel).getAllByText('Fallback 1')[0]).toBeVisible();
    expect(within(panel).getAllByText('Stale 1')[0]).toBeVisible();
    expect(within(panel).getAllByText('Estimated 1')[0]).toBeVisible();
    expect(within(panel).getAllByText('Partial 1')[0]).toBeVisible();
    expect(within(panel).getAllByText('Not supported 1')[0]).toBeVisible();

    fireEvent.click(within(panel).getAllByText('Input Blocks')[0]);

    const quoteBlock = screen.getByText('行情').closest('.home-subpanel');
    expect(quoteBlock).not.toBeNull();
    expect(within(quoteBlock as HTMLElement).getByText('Details: This analysis used a fallback data path; review the result against its source and warnings')).toBeInTheDocument();
    expect(within(quoteBlock as HTMLElement).queryByText(/^Action:/)).not.toBeInTheDocument();

    expect(screen.getByText('Details: This analysis used data that may not be current; check the timestamp and rerun if needed')).toBeInTheDocument();
    expect(screen.getByText('Details: Only part of the data was included, so related conclusions may be incomplete; check warnings and the data source and rerun')).toBeInTheDocument();
    expect(screen.getByText('Details: This analysis used estimated data; cross-check the result against source data')).toBeInTheDocument();
    expect(screen.getByText('Details: This data is not supported for the current market or symbol and was not used; cross-check other indicators')).toBeInTheDocument();
  });

  it('does not render without an overview', () => {
    const { container } = render(<AnalysisContextSummary overview={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not render raw values or unexpected sensitive fields', () => {
    const unsafeOverview = {
      ...overview,
      value: 'raw trend payload',
      content: '完整新闻正文不应出现',
      apiKey: 'secret-key',
      blocks: [
        {
          ...overview.blocks[0],
          items: {
            price: {
              value: 1880,
              apiKey: 'secret-key',
            },
          },
        },
      ],
    } as unknown as AnalysisContextPackOverview;

    render(<AnalysisContextSummary overview={unsafeOverview} />);

    fireEvent.click(screen.getAllByText('Input Blocks')[0]);

    expect(screen.queryByText('raw trend payload')).not.toBeInTheDocument();
    expect(screen.queryByText('完整新闻正文不应出现')).not.toBeInTheDocument();
    expect(screen.queryByText('secret-key')).not.toBeInTheDocument();
  });
});

describe('ReportSummary analysis context placement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders strategy and news before context, diagnostics and traceability', async () => {
    vi.mocked(historyApi.getNews).mockResolvedValue({
      total: 0,
      items: [],
    });

    const report: AnalysisReport = {
      meta: {
        id: 1,
        queryId: 'q1',
        stockCode: '600519',
        stockName: '贵州茅台',
        reportType: 'detailed',
        reportLanguage: 'zh',
        createdAt: '2026-04-10T12:00:00',
        marketPhaseSummary: {
          market: 'cn',
          phase: 'intraday',
          marketLocalTime: '2026-04-10T10:30:00+08:00',
          sessionDate: '2026-04-10',
          effectiveDailyBarDate: '2026-04-09',
          isTradingDay: true,
          isMarketOpenNow: true,
          isPartialBar: true,
          minutesToOpen: null,
          minutesToClose: 150,
          triggerSource: 'api',
          analysisIntent: 'auto',
          warnings: [],
        },
      },
      summary: {
        analysisSummary: 'summary',
        operationAdvice: '持有',
        trendPrediction: '震荡',
        sentimentScore: 70,
      },
      strategy: {
        idealBuy: '120',
      },
      details: {
        analysisContextPackOverview: overview,
        marketStructure,
      },
    };
    const result: AnalysisResult = {
      queryId: 'q1',
      stockCode: '600519',
      stockName: '贵州茅台',
      report,
      diagnosticSummary: {
        status: 'normal',
        statusLabel: '正常',
        reason: '运行正常',
        components: {},
        copyText: '',
      },
      createdAt: '2026-04-10T12:00:00',
    };

    render(<ReportSummary data={result} />);

    await waitFor(() => {
      expect(screen.getByText('暂无相关资讯')).toBeInTheDocument();
    });

    expect(screen.getByText('Piyasa Seansı: CN · Seans İçi')).toBeInTheDocument();
    expect(screen.getByText('Günlük Bar Tamamlanmadı')).toBeInTheDocument();
    expect(screen.getAllByText('质量分 82/100 可用')[0]).toBeInTheDocument();

    const strategy = screen.getByText('狙击点位');
    const news = screen.getByText('相关资讯');
    const diagnostics = screen.getByTestId('run-diagnostics');
    const contextSummary = screen.getByTestId('analysis-context-summary');
    expect(contextSummary).not.toHaveAttribute('open');
    expect(diagnostics).not.toHaveAttribute('open');
    const traceability = screen.getByText('数据追溯');

    expect(strategy.compareDocumentPosition(news) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(news.compareDocumentPosition(contextSummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(contextSummary.compareDocumentPosition(diagnostics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(diagnostics.compareDocumentPosition(traceability) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(within(contextSummary).getAllByText('输入数据块')[0]);
    expect(within(contextSummary).getByText(/说明: 新闻未进入本次 LLM 分析，结论未使用新闻上下文/)).toBeInTheDocument();
    expect(within(contextSummary).getByText(/报告页相关资讯由独立接口补充，显示与否不代表已进入本次分析/)).toBeInTheDocument();
    expect(screen.queryByText('AI 建议 / 决策信号')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '题材主线与个股位置' })).not.toBeInTheDocument();
    expect(screen.queryByText('Robotics')).not.toBeInTheDocument();
  });
});
