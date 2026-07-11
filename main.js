/* Shared scroll reveal used across every page */
const io = new IntersectionObserver((entries)=>{
  entries.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
},{threshold:.15});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

/* fire hero reveals immediately on load */
window.addEventListener('load',()=>{
  document.querySelectorAll('.hero .reveal').forEach(el=>el.classList.add('in'));
});
