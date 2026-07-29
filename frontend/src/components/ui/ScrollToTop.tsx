import { useState, useEffect } from 'react';
import { ArrowUp } from 'lucide-react';
import { cn } from '@/lib/utils';

export function ScrollToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      const windowScroll = window.scrollY || document.documentElement.scrollTop;
      const scrollables = document.querySelectorAll('.overflow-y-auto');
      let maxInternalScroll = 0;
      scrollables.forEach((el) => {
        if (el.scrollTop > maxInternalScroll) {
          maxInternalScroll = el.scrollTop;
        }
      });

      if (windowScroll > 150 || maxInternalScroll > 150) {
        setVisible(true);
      } else {
        setVisible(false);
      }
    };

    window.addEventListener('scroll', handleScroll, { capture: true, passive: true });
    // Run initial check
    handleScroll();

    return () => window.removeEventListener('scroll', handleScroll, { capture: true });
  }, []);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });

    const scrollables = document.querySelectorAll('.overflow-y-auto');
    scrollables.forEach((el) => {
      el.scrollTo({ top: 0, behavior: 'smooth' });
    });
  };

  return (
    <button
      type="button"
      onClick={scrollToTop}
      title="Remonter tout en haut"
      aria-label="Remonter tout en haut"
      className={cn(
        'fixed bottom-6 left-6 z-50 p-3 rounded-full shadow-xl transition-all duration-300 transform',
        'bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-110 active:scale-95',
        'border border-primary/20 backdrop-blur-md focus:outline-none focus:ring-2 focus:ring-primary/50',
        'flex items-center justify-center group cursor-pointer',
        visible ? 'opacity-100 translate-y-0 pointer-events-auto' : 'opacity-0 translate-y-4 pointer-events-none'
      )}
    >
      <ArrowUp className="h-5 w-5 transition-transform group-hover:-translate-y-1" />
    </button>
  );
}
