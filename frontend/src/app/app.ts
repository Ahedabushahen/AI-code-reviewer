import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { CodeInputComponent } from './components/code-input/code-input';
import { ReviewResultComponent, ReviewResult } from './components/review-result/review-result';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CodeInputComponent, ReviewResultComponent],
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
})
export class App {
  loading = false;
  result: ReviewResult | null = null;

  onReviewed(result: ReviewResult) {
    this.result = result;
  }
}
