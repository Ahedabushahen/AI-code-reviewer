import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import type { ReviewItem, ReviewResult } from '../review-result/review-result';

@Component({
  selector: 'app-code-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './code-input.html',
  styleUrls: ['./code-input.css'],
})
export class CodeInputComponent {
  @Output() reviewed = new EventEmitter<ReviewResult>();

  language = 'typescript';
  code = '';
  loading = false;

  async onReview() {
    this.loading = true;

    const result: ReviewResult = this.buildMockReview(this.language, this.code);

    await new Promise((r) => setTimeout(r, 350));
    this.loading = false;

    this.reviewed.emit(result);
  }

  private buildMockReview(language: string, code: string): ReviewResult {
    const empty = code.trim().length === 0;

    // Make arrays typed so "severity" stays 'low' | 'medium' | 'high'
    const bugs: ReviewItem[] = [];
    const security: ReviewItem[] = [];
    const performance: ReviewItem[] = [];
    const best_practices: ReviewItem[] = [];

    if (empty) {
      best_practices.push({
        title: 'Provide input code',
        description: 'Paste a snippet or file content to review.',
        severity: 'low',
      });

      return {
        score: 1,
        summary: 'No code provided. Paste some code to get a review.',
        bugs,
        security,
        performance,
        best_practices,
      };
    }

    // Simple heuristics for demo (replace with real AI later)
    const hasEval = /eval\s*\(/.test(code);
    const hasConsole = /console\.log/.test(code);
    const hasAny = /\bany\b/.test(code);
    const isLarge = code.length > 1200;

    if (hasEval) {
      security.push({
        title: 'Use of eval()',
        description:
          'Avoid eval() because it can execute untrusted code. Prefer safer parsing/validation approaches.',
        severity: 'high',
      });
    }

    if (hasConsole) {
      best_practices.push({
        title: 'Debug logging left in code',
        description:
          'Remove console.log statements or use a proper logger with log levels.',
        severity: 'low',
      });
    }

    if (hasAny && language === 'typescript') {
      best_practices.push({
        title: 'TypeScript "any" usage',
        description:
          'Consider replacing "any" with specific types or generics for better safety.',
        severity: 'medium',
      });
    }

    if (isLarge) {
      performance.push({
        title: 'Large input detected',
        description:
          'For large files, review diffs or specific sections to reduce noise and improve accuracy.',
        severity: 'low',
      });
    }

    // Score: start from 9 and reduce
    let score = 9;
    if (hasEval) score -= 4;
    if (hasAny && language === 'typescript') score -= 1;
    if (hasConsole) score -= 1;
    if (isLarge) score -= 1;
    if (score < 1) score = 1;

    return {
      score,
      summary:
        score >= 8
          ? 'Looks solid overall. Minor improvements recommended.'
          : score >= 5
          ? 'Some issues found. Fix these before merging.'
          : 'Several important issues found. Please refactor before merging.',
      bugs,
      security,
      performance,
      best_practices,
    };
  }
}
