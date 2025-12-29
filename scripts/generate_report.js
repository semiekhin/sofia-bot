const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, 
        Header, Footer, AlignmentType, BorderStyle, WidthType, 
        HeadingLevel, ShadingType, PageNumber } = require('docx');
const fs = require('fs');
const { execSync } = require('child_process');

// Получаем данные из баз
function query(db, sql) {
    try {
        return execSync(`sqlite3 -json "${db}" "${sql}"`, { encoding: 'utf8' });
    } catch (e) {
        return '[]';
    }
}

// GPT данные
const gptStats = JSON.parse(query('/opt/sofia-bot/sofia_conversations.db', 
    `SELECT COUNT(DISTINCT expert_name) as experts, COUNT(DISTINCT chat_id) as dialogs, COUNT(*) as total,
     SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) as good,
     SUM(CASE WHEN rating='bad' THEN 1 ELSE 0 END) as bad
     FROM feedback_v2 WHERE timestamp >= '2025-12-18'`))[0] || {};

const gptExperts = JSON.parse(query('/opt/sofia-bot/sofia_conversations.db',
    `SELECT expert_name, COUNT(*) as cnt, 
     SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) as good,
     SUM(CASE WHEN rating='bad' THEN 1 ELSE 0 END) as bad,
     MIN(DATE(timestamp)) as first_date, MAX(DATE(timestamp)) as last_date
     FROM feedback_v2 WHERE timestamp >= '2025-12-18' GROUP BY expert_name ORDER BY cnt DESC`));

const gptFeedback = JSON.parse(query('/opt/sofia-bot/sofia_conversations.db',
    `SELECT timestamp, expert_name, rating, chat_id, comment 
     FROM feedback_v2 WHERE timestamp >= '2025-12-18' ORDER BY timestamp DESC`));

// Claude данные
const claudeStats = JSON.parse(query('/opt/sofia-claude/sofia_conversations.db',
    `SELECT COUNT(DISTINCT expert_name) as experts, COUNT(DISTINCT chat_id) as dialogs, COUNT(*) as total,
     SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) as good,
     SUM(CASE WHEN rating='bad' THEN 1 ELSE 0 END) as bad
     FROM feedback_v2`))[0] || {};

const claudeExperts = JSON.parse(query('/opt/sofia-claude/sofia_conversations.db',
    `SELECT expert_name, COUNT(*) as cnt,
     SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) as good,
     SUM(CASE WHEN rating='bad' THEN 1 ELSE 0 END) as bad,
     MIN(DATE(timestamp)) as first_date, MAX(DATE(timestamp)) as last_date
     FROM feedback_v2 GROUP BY expert_name ORDER BY cnt DESC`));

const claudeFeedback = JSON.parse(query('/opt/sofia-claude/sofia_conversations.db',
    `SELECT timestamp, expert_name, rating, chat_id, comment 
     FROM feedback_v2 ORDER BY timestamp DESC`));

// Стили таблицы
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

function makeCell(text, opts = {}) {
    return new TableCell({
        borders: cellBorders,
        width: { size: opts.width || 2000, type: WidthType.DXA },
        shading: opts.header ? { fill: "2E75B6", type: ShadingType.CLEAR } : undefined,
        children: [new Paragraph({
            alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
            children: [new TextRun({ 
                text: String(text || '—'), 
                bold: opts.header || opts.bold,
                color: opts.header ? "FFFFFF" : "000000",
                size: 20
            })]
        })]
    });
}

function makeStatsTable(stats, title) {
    const goodRate = stats.total ? ((stats.good / stats.total) * 100).toFixed(1) : 0;
    return new Table({
        columnWidths: [3500, 2500],
        rows: [
            new TableRow({ children: [
                makeCell(title, { header: true, width: 3500 }),
                makeCell('Значение', { header: true, width: 2500, center: true })
            ]}),
            new TableRow({ children: [makeCell('Тестировщиков', { width: 3500 }), makeCell(stats.experts, { width: 2500, center: true })]}),
            new TableRow({ children: [makeCell('Диалогов', { width: 3500 }), makeCell(stats.dialogs, { width: 2500, center: true })]}),
            new TableRow({ children: [makeCell('Всего оценок', { width: 3500 }), makeCell(stats.total, { width: 2500, center: true })]}),
            new TableRow({ children: [makeCell('✅ GOOD', { width: 3500 }), makeCell(`${stats.good} (${goodRate}%)`, { width: 2500, center: true })]}),
            new TableRow({ children: [makeCell('❌ BAD', { width: 3500 }), makeCell(`${stats.bad} (${(100 - goodRate).toFixed(1)}%)`, { width: 2500, center: true })]})
        ]
    });
}

function makeExpertsTable(experts) {
    const rows = [new TableRow({ children: [
        makeCell('Эксперт', { header: true, width: 2500 }),
        makeCell('Оценок', { header: true, width: 1200, center: true }),
        makeCell('✅', { header: true, width: 800, center: true }),
        makeCell('❌', { header: true, width: 800, center: true }),
        makeCell('Первая', { header: true, width: 1500, center: true }),
        makeCell('Последняя', { header: true, width: 1500, center: true })
    ]})];
    
    experts.forEach(e => {
        rows.push(new TableRow({ children: [
            makeCell(e.expert_name, { width: 2500 }),
            makeCell(e.cnt, { width: 1200, center: true }),
            makeCell(e.good, { width: 800, center: true }),
            makeCell(e.bad, { width: 800, center: true }),
            makeCell(e.first_date, { width: 1500, center: true }),
            makeCell(e.last_date, { width: 1500, center: true })
        ]}));
    });
    return new Table({ columnWidths: [2500, 1200, 800, 800, 1500, 1500], rows });
}

function makeFeedbackTable(feedback) {
    const rows = [new TableRow({ children: [
        makeCell('Время', { header: true, width: 2200 }),
        makeCell('Эксперт', { header: true, width: 1500 }),
        makeCell('Оценка', { header: true, width: 900, center: true }),
        makeCell('Диалог', { header: true, width: 1000, center: true }),
        makeCell('Комментарий', { header: true, width: 3700 })
    ]})];
    
    feedback.forEach(f => {
        rows.push(new TableRow({ children: [
            makeCell(f.timestamp?.substring(0, 16), { width: 2200 }),
            makeCell(f.expert_name, { width: 1500 }),
            makeCell(f.rating === 'good' ? '✅' : '❌', { width: 900, center: true }),
            makeCell(`#${f.chat_id}`, { width: 1000, center: true }),
            makeCell((f.comment || '—').substring(0, 50), { width: 3700 })
        ]}));
    });
    return new Table({ columnWidths: [2200, 1500, 900, 1000, 3700], rows });
}

const today = new Date().toISOString().split('T')[0];

const doc = new Document({
    styles: {
        default: { document: { run: { font: "Arial", size: 22 } } },
        paragraphStyles: [
            { id: "Title", name: "Title", basedOn: "Normal",
              run: { size: 48, bold: true, color: "2E75B6" },
              paragraph: { spacing: { after: 200 }, alignment: AlignmentType.CENTER } },
            { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 32, bold: true, color: "2E75B6" },
              paragraph: { spacing: { before: 400, after: 200 } } },
            { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 26, bold: true, color: "404040" },
              paragraph: { spacing: { before: 300, after: 150 } } }
        ]
    },
    sections: [{
        properties: { page: { margin: { top: 1000, right: 1000, bottom: 1000, left: 1000 } } },
        headers: { default: new Header({ children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "Sofia Bot — Отчёт по обучению", size: 18, color: "888888" })]
        })] }) },
        footers: { default: new Footer({ children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: "Страница ", size: 18 }), new TextRun({ children: [PageNumber.CURRENT], size: 18 }),
                       new TextRun({ text: " из ", size: 18 }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18 })]
        })] }) },
        children: [
            // Заголовок
            new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("Отчёт по обучению бота-менеджера Sofia")] }),
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
                children: [new TextRun({ text: `Дата формирования: ${today}`, size: 20, color: "666666" })] }),
            
            // GPT секция
            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("🤖 GPT-5.2 — @SofiaOazisBot")] }),
            new Paragraph({ children: [new TextRun({ text: "Период: с 18 декабря 2025", italics: true, color: "666666" })] }),
            new Paragraph({ spacing: { before: 200 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Общая статистика")] }),
            makeStatsTable(gptStats, 'Метрика'),
            new Paragraph({ spacing: { before: 300 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Тестировщики")] }),
            makeExpertsTable(gptExperts),
            new Paragraph({ spacing: { before: 300 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Все оценки")] }),
            makeFeedbackTable(gptFeedback),
            
            // Claude секция
            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("🧠 Claude Sonnet 4 — @humanClaudeAINeural_bot")] }),
            new Paragraph({ children: [new TextRun({ text: "Период: все данные", italics: true, color: "666666" })] }),
            new Paragraph({ spacing: { before: 200 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Общая статистика")] }),
            makeStatsTable(claudeStats, 'Метрика'),
            new Paragraph({ spacing: { before: 300 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Тестировщики")] }),
            makeExpertsTable(claudeExperts),
            new Paragraph({ spacing: { before: 300 } }),
            
            new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Все оценки")] }),
            makeFeedbackTable(claudeFeedback),
            
            // Сравнение
            new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("📊 Сравнение GPT vs Claude")] }),
            new Table({
                columnWidths: [3000, 2500, 2500],
                rows: [
                    new TableRow({ children: [
                        makeCell('Метрика', { header: true, width: 3000 }),
                        makeCell('GPT-5.2', { header: true, width: 2500, center: true }),
                        makeCell('Claude', { header: true, width: 2500, center: true })
                    ]}),
                    new TableRow({ children: [
                        makeCell('🎯 GOOD rate', { width: 3000, bold: true }),
                        makeCell(`${gptStats.total ? ((gptStats.good/gptStats.total)*100).toFixed(1) : 0}%`, { width: 2500, center: true }),
                        makeCell(`${claudeStats.total ? ((claudeStats.good/claudeStats.total)*100).toFixed(1) : 0}%`, { width: 2500, center: true })
                    ]}),
                    new TableRow({ children: [
                        makeCell('📝 Всего оценок', { width: 3000 }),
                        makeCell(gptStats.total, { width: 2500, center: true }),
                        makeCell(claudeStats.total, { width: 2500, center: true })
                    ]}),
                    new TableRow({ children: [
                        makeCell('💬 Диалогов', { width: 3000 }),
                        makeCell(gptStats.dialogs, { width: 2500, center: true }),
                        makeCell(claudeStats.dialogs, { width: 2500, center: true })
                    ]}),
                    new TableRow({ children: [
                        makeCell('👥 Тестировщиков', { width: 3000 }),
                        makeCell(gptStats.experts, { width: 2500, center: true }),
                        makeCell(claudeStats.experts, { width: 2500, center: true })
                    ]})
                ]
            })
        ]
    }]
});

Packer.toBuffer(doc).then(buffer => {
    const path = `/opt/sofia-bot/reports/training_report_${today}.docx`;
    fs.mkdirSync('/opt/sofia-bot/reports', { recursive: true });
    fs.writeFileSync(path, buffer);
    console.log(`✅ Отчёт сохранён: ${path}`);
});
