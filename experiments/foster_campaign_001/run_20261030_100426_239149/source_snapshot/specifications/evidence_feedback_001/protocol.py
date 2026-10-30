"""Generic in-process evidence ownership, without a battery or test harness.

The supplied backend must be pure: it evaluates immutable payloads and returns
an immutable candidate. Representation arithmetic is not implemented here.
"""
from dataclasses import dataclass, asdict
import hashlib
import json

UINT64_MAX = 2**64-1


class ContractError(ValueError):
    pass


def uint(value, label):
    if type(value) is not int or not 0 <= value <= UINT64_MAX:
        raise ContractError(label+' must be uint64')


def identity(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ContractError('identity must be lowercase SHA256 hex')


def digest(value):
    def encode(x):
        if type(x) is bytes:
            return {'bytes':len(x), 'sha256':hashlib.sha256(x).hexdigest()}
        raise TypeError(type(x).__name__)
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=encode,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Binding:
    source_id: str
    model_id: str
    chart_id: str
    noise_id: str
    calibration_id: str
    evolution_id: str
    domain_id: str
    representation_id: str
    dimension: int
    tick_hz: int

    def __post_init__(self):
        for name,value in asdict(self).items():
            if name.endswith('_id'):identity(value)
        uint(self.dimension,'dimension');uint(self.tick_hz,'tick_hz')
        if self.dimension==0 or self.tick_hz==0:raise ContractError('zero dimension or clock')


@dataclass(frozen=True)
class Boundary:
    sequence: int
    ticks: int

    def __post_init__(self):
        uint(self.sequence,'sequence');uint(self.ticks,'ticks')


def payload_check(payload):
    if type(payload) is not bytes or not payload:raise ContractError('nonempty immutable payload required')


def tier_check(tier):
    if tier not in ('exact_declared_family','local_approximate'):
        raise ContractError('unsupported approximation tier')


@dataclass(frozen=True)
class EvidenceToken:
    binding: Binding
    entry: Boundary
    exit: Boundary
    base_feedback_id: str
    payload: bytes
    tier: str = 'local_approximate'
    kind: str = 'prior_free_conditional_kernel'
    includes_root_prior: bool = False
    includes_feedback: bool = False

    def __post_init__(self):
        if type(self.binding) is not Binding or type(self.entry) is not Boundary or type(self.exit) is not Boundary:
            raise ContractError('typed binding and boundaries required')
        identity(self.base_feedback_id);payload_check(self.payload);tier_check(self.tier)
        if self.kind!='prior_free_conditional_kernel' or self.includes_root_prior is not False or self.includes_feedback is not False:
            raise ContractError('only prior-free, feedback-free kernels are admissible')
        if self.exit.sequence<=self.entry.sequence or self.exit.ticks<self.entry.ticks:
            raise ContractError('empty or reversed retirement interval')

    @property
    def token_id(self):return digest(asdict(self))


@dataclass(frozen=True)
class FeedbackMessage:
    binding: Binding
    root_prior_id: str
    generation: int
    boundary: Boundary
    payload: bytes
    tier: str
    ledger_id: str
    error_bound: object = None
    coverage_validated: bool = False

    def __post_init__(self):
        if type(self.binding) is not Binding or type(self.boundary) is not Boundary:raise ContractError('typed feedback binding')
        identity(self.root_prior_id);identity(self.ledger_id);uint(self.generation,'generation')
        payload_check(self.payload);tier_check(self.tier)
        if self.error_bound is not None or self.coverage_validated is not False:
            raise ContractError('reference supplies neither certified error nor coverage')

    @property
    def message_id(self):return digest(asdict(self))


@dataclass(frozen=True)
class Receipt:
    token_id: str
    base_message_id: str
    new_message_id: str
    entry: Boundary
    exit: Boundary
    generation: int


class History:
    """One authoritative message, one staged candidate, one retry receipt.

    Caller serializes operations. This is not durable storage or a total SRAM
    allocator. max_payload_bytes limits each message payload, not peak memory.
    Backend validate/advance must reject invalid numeric content and preserve
    normalizers, joint dependence and any declared approximation accounting.
    """
    def __init__(self,binding,root_prior_id,prior_payload,backend,max_payload_bytes,tier='local_approximate'):
        uint(max_payload_bytes,'capacity')
        if max_payload_bytes==0:raise ContractError('zero capacity')
        self._backend=backend;self._capacity=max_payload_bytes
        self._validate(prior_payload)
        self._head=FeedbackMessage(binding,root_prior_id,0,Boundary(0,0),prior_payload,tier,
                                   digest({'root_prior':root_prior_id,'payload':prior_payload}))
        self._pending=None;self._last=None

    def _validate(self,payload):
        payload_check(payload)
        if len(payload)>self._capacity:raise ContractError('message payload capacity exceeded')
        self._backend.validate_message(payload)

    def read(self):return self._head

    def prepare(self,token,observed_end):
        if type(token) is not EvidenceToken:raise ContractError('estimate or feedback is not new evidence')
        uint(observed_end,'observed_end')
        head=self._head
        if token.binding!=head.binding:raise ContractError('immutable binding mismatch')
        if token.base_feedback_id!=head.message_id:raise ContractError('stale base feedback')
        if token.entry!=head.boundary:raise ContractError('overlap, gap or epoch mismatch')
        if token.exit.sequence>observed_end:raise ContractError('unreceived future observations')
        if self._pending:
            if self._pending[0]==token.token_id:return token.token_id
            raise ContractError('another retirement is pending')
        if head.generation==UINT64_MAX:raise ContractError('generation exhausted')
        candidate=self._backend.advance(head.payload,token)
        self._validate(candidate)
        tier='exact_declared_family' if head.tier==token.tier=='exact_declared_family' else 'local_approximate'
        message=FeedbackMessage(head.binding,head.root_prior_id,head.generation+1,token.exit,candidate,tier,
             digest({'previous_ledger':head.ledger_id,'token':token.token_id,'result':candidate}))
        receipt=Receipt(token.token_id,head.message_id,message.message_id,token.entry,token.exit,message.generation)
        self._pending=(token.token_id,message,receipt)
        return token.token_id

    def commit(self,ticket):
        identity(ticket)
        if self._last is not None and ticket==self._last.token_id:return self._last
        if self._pending is None or ticket!=self._pending[0]:raise ContractError('unknown retirement ticket')
        _,candidate,receipt=self._pending
        # Assignment is the publication point for the externally serialized API.
        self._head=candidate;self._last=receipt;self._pending=None
        return receipt

    def abort(self,ticket):
        if self._pending is None or ticket!=self._pending[0]:raise ContractError('unknown pending ticket')
        self._pending=None


class WindowOwnership:
    """Producer's metadata only; actual raw-window storage remains external."""
    def __init__(self,feedback):
        if type(feedback) is not FeedbackMessage:raise ContractError('feedback required')
        self.binding=feedback.binding;self.start=feedback.boundary;self.end=self.start.sequence
        self.feedback_id=feedback.message_id

    def offer(self,sequence):
        uint(sequence,'sequence')
        if sequence!=self.end or self.end==UINT64_MAX:raise ContractError('source order or overflow')
        self.end+=1

    def query_scope(self,feedback):
        if (feedback.binding!=self.binding or feedback.message_id!=self.feedback_id or feedback.boundary!=self.start):
            raise ContractError('reconcile committed retirement before querying')
        return self.start.sequence,self.end

    def acknowledge(self,receipt,feedback):
        if type(receipt) is not Receipt or type(feedback) is not FeedbackMessage:raise ContractError('receipt and feedback required')
        if (feedback.binding!=self.binding or receipt.new_message_id!=feedback.message_id or
            receipt.exit!=feedback.boundary or receipt.generation!=feedback.generation or receipt.exit.sequence>self.end):
            raise ContractError('inconsistent receipt or future retirement')
        if self.feedback_id==feedback.message_id and self.start==receipt.exit:return
        if receipt.base_message_id!=self.feedback_id or receipt.entry!=self.start:
            raise ContractError('receipt does not retire current prefix')
        self.start=receipt.exit;self.feedback_id=feedback.message_id
