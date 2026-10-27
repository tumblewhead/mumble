async ({presentation}) => {
  if (presentation.slides.items.length !== 1) throw new Error("Expected the reserved one-slide document");
  const ink="#173044", teal="#126E8A", muted="#52616C";
  function text(slide,name,value,x,y,w,h,size,bold=false,color=ink) {
    const s=slide.shapes.add({geometry:"textbox",name,position:{left:x,top:y,width:w,height:h},
      fill:"none",line:{style:"solid",fill:"none",width:0}});
    s.text=value;s.text.style={fontSize:size,bold,color,typeface:"Arial",insets:0,wrap:"none",autoFit:"none",verticalAlignment:"middle"};
    return s;
  }
  function rect(slide,name,x,y,w,h,fill) {
    return slide.shapes.add({geometry:"rect",name,position:{left:x,top:y,width:w,height:h},
      fill,line:{style:"solid",fill:"none",width:0}});
  }
  function base(slide,label,title,subtitle,index) {
    slide.background.fill="#FFFFFF";
    text(slide,"section",label,48,22,1184,24,13,true,teal);
    text(slide,"title",title,48,52,1184,56,38,true);
    text(slide,"subtitle",subtitle,48,111,1184,31,18,false,muted);
    text(slide,"source","Mumble · live_anchor_integration_001 · source 6e60b8f · "+index+"/3",
      48,697,1184,16,10.5,false,muted);
  }
  const s0=presentation.slides.items[0];
  base(s0,"RESEARCH UPDATE","Rolling estimation reaches useful point accuracy",
    "4-hour synthetic stream · Public start · 504,000 samples · 12-bit V/I/T",1);
  const cards=[
    [48,"Final capacity","64.659 mAh","−0.0628% relative error"],
    [456,"Final SOC error","−0.00942 pp","Current SOC: 42.3223%"],
    [864,"Owned context","8,680 B","10,216 B total memory plan"]
  ];
  for(const [x,label,value,detail] of cards) {
    rect(s0,label+" card",x,156,368,100,"#EFF6F7");
    text(s0,label+" label",label,x+18,167,332,21,14,true,muted);
    text(s0,label+" value",value,x+18,189,332,35,29,true);
    text(s0,label+" detail",detail,x+18,227,332,20,14,false,muted);
  }
  s0.images.add({path:"library-file:fde1_bGliZmlsZV80dHNzcWNvbUNBNlNKYm9rUW5TQWJ3_FileDrive_556d01f2e24c8191b869c6d3916c71e4",alt:"Full four-hour capacity-relative-error and current-SOC percentage-point-error traces. Every saved point is included, with declared preferred and hard performance limits.",fit:"contain",position:{left:40,top:271,width:1200,height:352.5}});
  text(s0,"preferred retained","Preferred limits retained on the remaining saved grid: SOC from 17.8 min · Capacity from 33.0 min",
    48,632,1184,27,17,true,teal);
  text(s0,"limits","Several nuisance parameters remain biased. Intervals and Cortex-M23 resources are still unqualified.",
    48,665,1184,23,15,false,muted);
  s0.speakerNotes.text="One complete public-start causal run: 504,000 chronological observations, 31,500 committed blocks and 31,501 snapshots. Incoming V/I/T are 12-bit codes with actual interval ticks under an explicitly synthetic calibration. The estimator owns one history factor, 16 raw working records and 8 ingress records. File playback, full trace storage and later exact audits are host-only. Final capacity is 64.6593630381 mAh versus 64.7 mAh (−0.0628082873%); final current SOC is 42.3222973868% versus 42.3317141385% (−0.00941675171 percentage points). Capacity first enters its preferred ±0.5% range at 12 min, leaves it, and stays within from 33.005714 min on the remaining saved block grid. SOC stays within ±0.5 percentage points from 17.76 min. These are finite saved-grid performance screens, not eventual-convergence or coverage claims. Every block accepts one full step and stops at the one-round budget. The independently qualified context is 8,680 B; the measured host source-owned stack path is 760 B, within the 768 B reservation. Adding a separate unmeasured 768 B runtime/IRQ/caller allowance gives the 10,216 B plan, only 24 B below 10 KiB. Complete M23 ABI/linker/stack/timing measurements remain open. Voltage quantization RMS is 0.281845 mV; current and time happen to quantize essentially exactly in this stimulus, and temperature is fixed at25 C without compensation. Three fixed-point exact-history checks found represented-minus-exact costs −5894.9361, −5863.6373 and +8938.5397 at2h,2h20m and4h. These absolute offsets alone do not establish likelihood-shape or interval distortion. Next: local joint likelihood-shape diagnostics around the internally learned anchor, then validated uncertainty. Sources: experiments/live_anchor_integration_001/reporting_continuation001/summary.json, postclosure_audit001/result.json, review/result_review.json and review/execution_receipt_review_v2.json.";
  const s1=presentation.slides.add({width:1280,height:720});
  base(s1,"APPENDIX · ORIGINAL ENTERING QUANTITIES","All 16 quantities, part 1",
    "Solid teal: estimate · Dashed amber: source reference · Every saved block shown",2);
  s1.images.add({path:"library-file:fde1_bGliZmlsZV8wbzhkT2ZORVl2VXljVmJlak53SjBB_FileDrive_556d01f2e24c8191b869c6d3916c71e4",alt:"Parameters1 through8 over all four hours: three RC time constants, two hysteresis rates, capacity and resistancesR0 andR1, with source reference lines.",fit:"contain",position:{left:30,top:147,width:1220,height:537.56}});
  s1.speakerNotes.text="These are original entering-chart quantities transformed to physical units. All31,501 snapshots are shown without smoothing. Parameter motion and accurate final values do not establish convergence. Final tau1 is0.0944973 s versus0.075 s (+25.9964%), tau2 is0.705143 s versus0.65 s (+8.4836%), and R0 is0.179998 ohm versus0.16 ohm (+12.4986%). These nuisance errors coexist with useful final capacity and SOC point accuracy. The fast RC/resistance parameters are not all identified by this finite integration. Reference values are external synthetic-source truth read only after inference closure. The same full16D chart/prior is retained throughout; no saved fitted anchor initializes the candidate. See reporting_continuation001/summary.json for all coordinate values and signed errors.";
  const s2=presentation.slides.add({width:1280,height:720});
  base(s2,"APPENDIX · ORIGINAL ENTERING QUANTITIES","All 16 quantities, part 2",
    "Entering states retain their original meaning; they are separate from the changing current states.",3);
  s2.images.add({path:"library-file:fde1_bGliZmlsZV9zSUd6SEpzbHB1WG5XNTlMeDhXVDlB_FileDrive_556d01f2e24c8191b869c6d3916c71e4",alt:"Parameters9 through16 over all four hours: resistancesR2/R3, hysteresis amplitudeH, enteringSOC, entering polarization voltagesv1/v2/v3 and enteringh, with source references.",fit:"contain",position:{left:30,top:147,width:1220,height:537.56}});
  s2.speakerNotes.text="The five entering states remain the states at the original beginning of this stream; they are never reset at a rolling-block boundary. Current SOC/v1/v2/v3/h are separate derived outputs. Current SOC has a complete reference trace. Later current polarization/hysteresis truth is unavailable locally because the optional source-state journal is absent; their full estimate traces and explicit reference limitations are available in reporting001/current_states.png. Several entering-state estimates remain biased even where traces flatten. This result supports causal compact-history point estimation on this one synthetic study, not calibrated intervals, global identifiability or M3 promotion. All uncertainty conclusions remain separate from optimization curvature.";
  return {slide_ids:presentation.slides.items.map((s,i)=>({index:i,id:s.id})),images:presentation.getPendingImageHydrationRequests().map(x=>({uri:x.uri,slideIds:x.slideIds})),slides:3};
}
