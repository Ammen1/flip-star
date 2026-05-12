import { useState, useRef, useEffect } from 'react';

/**
 * SwipeablePages - Horizontal swipe navigation between pages (mobile)
 * Usage: Wrap multiple page components and swipe left/right to navigate
 */
export function SwipeablePages({ pages, activeIndex, onIndexChange, children }) {
  const [touchStart, setTouchStart] = useState(0);
  const [touchEnd, setTouchEnd] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const containerRef = useRef(null);

  const MIN_SWIPE_DISTANCE = 50; // Minimum distance for swipe
  const SWIPE_THRESHOLD = 80; // Threshold to trigger page change

  const handleTouchStart = (e) => {
    setTouchStart(e.targetTouches[0].clientX);
    setTouchEnd(e.targetTouches[0].clientX);
    setIsDragging(true);
  };

  const handleTouchMove = (e) => {
    if (!isDragging) return;
    const currentTouch = e.targetTouches[0].clientX;
    setTouchEnd(currentTouch);
    
    const distance = currentTouch - touchStart;
    // Prevent swiping beyond boundaries
    if ((activeIndex === 0 && distance > 0) || (activeIndex === pages.length - 1 && distance < 0)) {
      setDragOffset(distance * 0.2); // Reduced resistance at edges
    } else {
      setDragOffset(distance);
    }
  };

  const handleTouchEnd = () => {
    if (!isDragging) return;
    setIsDragging(false);
    
    const distance = touchStart - touchEnd;
    const isLeftSwipe = distance > MIN_SWIPE_DISTANCE;
    const isRightSwipe = distance < -MIN_SWIPE_DISTANCE;

    if (isLeftSwipe && Math.abs(distance) > SWIPE_THRESHOLD && activeIndex < pages.length - 1) {
      // Swipe left - next page
      onIndexChange?.(activeIndex + 1);
    } else if (isRightSwipe && Math.abs(distance) > SWIPE_THRESHOLD && activeIndex > 0) {
      // Swipe right - previous page
      onIndexChange?.(activeIndex - 1);
    }
    
    // Reset
    setDragOffset(0);
    setTouchStart(0);
    setTouchEnd(0);
  };

  const translateX = isDragging 
    ? dragOffset 
    : -activeIndex * 100;

  return (
    <div
      ref={containerRef}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        position: 'relative',
        touchAction: 'pan-y', // Allow vertical scrolling but handle horizontal
      }}
    >
      <div
        style={{
          display: 'flex',
          width: `${pages.length * 100}%`,
          height: '100%',
          transform: `translateX(${translateX}%)`,
          transition: isDragging ? 'none' : 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          willChange: 'transform',
        }}
      >
        {pages.map((page, index) => (
          <div
            key={page.id || index}
            style={{
              width: `${100 / pages.length}%`,
              height: '100%',
              flexShrink: 0,
              overflow: 'hidden',
            }}
          >
            {page.component}
          </div>
        ))}
      </div>
    </div>
  );
}




