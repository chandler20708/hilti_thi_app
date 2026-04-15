APP_CSS = """
<style>
  .main .block-container {
    padding-top: 1.3rem;
    padding-bottom: 2rem;
    max-width: 1520px;
  }

  .hero {
    padding: 1.35rem 1.4rem;
    border-radius: 22px;
    background: linear-gradient(135deg, #f7fbf8 0%, #eef8f3 100%);
    border: 1px solid rgba(16, 24, 40, 0.08);
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
    margin-bottom: 0.5rem;
  }

  .hero h1 {
    margin: 0;
    color: #122317;
    font-size: 2.2rem;
    line-height: 1.1;
  }

  .hero-meta {
    margin-top: 0.75rem;
    color: #475467;
    font-size: 0.9rem;
  }

  .shell {
    background: #ffffff;
    border: 1px solid rgba(16, 24, 40, 0.08);
    border-radius: 20px;
    padding: 1rem 1.1rem;
    box-shadow: 0 16px 34px rgba(15, 23, 42, 0.06);
  }

  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(16, 24, 40, 0.08) !important;
    border-radius: 20px !important;
    box-shadow: 0 16px 34px rgba(15, 23, 42, 0.06);
    padding: 0.35rem 0.5rem;
  }

  div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: transparent;
  }

  .section-gap {
    height: 1rem;
  }

  .control-shell {
    background: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%);
    border: 1px solid rgba(16, 24, 40, 0.08);
    border-radius: 20px;
    padding: 1rem 1.1rem 0.2rem 1.1rem;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
    margin: 0.8rem 0 1rem 0;
  }

  .metric-card {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(16, 24, 40, 0.08);
    border-radius: 16px;
    padding: 1rem;
    min-height: 140px;          /* 👈 more space */
    display: flex;
    flex-direction: column;
    justify-content: space-between;  /* 👈 pushes chart to bottom */
  }

  .metric-spark {
    margin-top: 0.5rem;
    opacity: 0.7;
  }

  .metric-label { color: #475467; font-size: 0.9rem; margin-bottom: 0.4rem; }
  .metric-value { color: #101828; font-size: 2rem; font-weight: 700; line-height: 1.1; margin-bottom: 0.25rem; }
  .metric-subtext { color: #667085; font-size: 0.88rem; }
  .muted { color: #475467; }
  .chip {
    display: inline-block;
    padding: 0.24rem 0.6rem;
    border-radius: 999px;
    background: #ecfdf3;
    color: #027a48;
    font-size: 0.78rem;
    font-weight: 700;
    margin-right: 0.35rem;
  }

  .detail-card {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(16, 24, 40, 0.08);
    border-radius: 18px;
    padding: 1rem;
    margin-bottom: 0.9rem;
  }

  .detail-kicker {
    color: #475467;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.3rem;
  }

  .detail-card h3 {
    margin: 0 0 0.8rem 0;
    color: #101828;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
  }

  .detail-grid div {
    background: #ffffff;
    border: 1px solid rgba(16, 24, 40, 0.06);
    border-radius: 14px;
    padding: 0.75rem;
  }

  .detail-grid span {
    display: block;
    color: #667085;
    font-size: 0.78rem;
    margin-bottom: 0.25rem;
  }

  .detail-grid strong {
    color: #101828;
    font-size: 1rem;
  }
</style>
"""
