/* Link/sizeof probe only: no startup, board, acquisition or execution claim. */
#include <stdint.h>
extern int foster_predict(const double *,const double *,int,const double *,double *,double *,double *,double *);
struct buffers {
    double message[273];
    double point[16], observations[80], calibration[14];
    double voltage[16], jacobian[256], endpoint[16], transport[256];
};
struct buffers probe;
volatile int probe_status;
void probe_entry(void) {
    probe.point[0]=probe.message[0];
    probe_status=foster_predict(probe.point,probe.observations,16,probe.calibration,
        probe.voltage,probe.jacobian,probe.endpoint,probe.transport);
    for (;;) { }
}
