import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export type ReviewItem = {
  title: string;
  description: string;
  severity: 'low' | 'medium' | 'high';
};

export type ReviewResult = {
  score: number; // 1-10
  summary: string;
  bugs: ReviewItem[];
  security: ReviewItem[];
  performance: ReviewItem[];
  best_practices: ReviewItem[];
};

@Component({
  selector: 'app-review-result',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './review-result.html',
  styleUrls: ['./review-result.css'],
})
export class ReviewResultComponent {
  @Input() result: ReviewResult | null = null;
  @Input() loading = false;
}
