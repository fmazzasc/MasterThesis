#!/usr/bin/env python3
import os
import pickle
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import ROOT
import uproot
import yaml
from helpers import significance_error, ndarray2roo

SPLIT = True

# avoid pandas warning
warnings.simplefilter(action='ignore', category=FutureWarning)
ROOT.gROOT.SetBatch()

##################################################################
# read configuration file
##################################################################
config = 'config.yaml'
with open(os.path.expandvars(config), 'r') as stream:
    try:
        params = yaml.full_load(stream)
    except yaml.YAMLError as exc:
        print(exc)

DATA_PATH = params['DATA_PATH']
CT_BINS = params['CT_BINS']
CENTRALITY_LIST = params['CENTRALITY_LIST']
RANDOM_STATE = params['RANDOM_STATE']
##################################################################

# split matter/antimatter
SPLIT_LIST = ['']
if SPLIT:
    SPLIT_LIST = ['antimatter', 'matter']

score_eff_arrays_dict = pickle.load(open("file_score_eff_dict", "rb"))
eff_array = np.arange(0.10, 0.91, 0.01)

for split in SPLIT_LIST:
    for i_cent_bins in range(len(CENTRALITY_LIST)):
        cent_bins = CENTRALITY_LIST[i_cent_bins]
        for ct_bins in zip(CT_BINS[i_cent_bins][:-1], CT_BINS[i_cent_bins][1:]):

            bin = f'{split}_{cent_bins[0]}_{cent_bins[1]}_{ct_bins[0]}_{ct_bins[1]}'
            df_data = pd.read_parquet(f'df/{bin}')
            df_signal = pd.read_parquet(f'df/mc_{bin}')

            # ROOT.Math.MinimizerOptions.SetDefaultTolerance(1e-2)
            root_file_signal_extraction = ROOT.TFile("SignalExtraction.root", "update")
            root_file_signal_extraction.mkdir(f'{bin}')

            for eff_score in zip(eff_array, score_eff_arrays_dict[bin]):
                if (ct_bins[0] > 0) and (eff_score[0] > 0.50):
                    continue
                formatted_eff = "{:.2f}".format(1-eff_score[0])
                print(f'processing {bin}: eff = {1-eff_score[0]:.2f}, score = {eff_score[1]:.2f}...')

                df_data_sel = df_data.query(f'model_output > {eff_score[1]}')
                df_signal_sel = df_signal.query(f'model_output > {eff_score[1]} and y_true == 1')
                if np.count_nonzero(df_signal_sel['y_true'] == 1) > 10000:
                    print('Sampling 10000 events...')
                    df_signal_sel = df_signal_sel.sample(10000)

                # get invariant mass distribution (data and mc)
                roo_m = ROOT.RooRealVar("m", "#it{M} (^{3}He + #pi^{-})", 2.96, 3.04, "GeV/#it{c}^{2}")
                roo_mc_m = ROOT.RooRealVar("m", "#it{M} (^{3}He + #pi^{-})", 2.96, 3.04, "GeV/#it{c}^{2}")
                roo_data = ndarray2roo(np.array(df_data_sel['m']), roo_m)
                roo_mc_signal = ndarray2roo(np.array(df_signal_sel['m']), roo_m)

                # declare fit model
                # kde
                roo_n_signal = ROOT.RooRealVar('Nsignal', 'N_{signal}', 5., 1., 50.)
                delta_mass = ROOT.RooRealVar("deltaM", '#Deltam', -0.004, 0.004, 'GeV/c^{2}')
                shifted_mass = ROOT.RooAddition("mPrime", "m + #Deltam", ROOT.RooArgList(roo_m, delta_mass))
                roo_signal = ROOT.RooKeysPdf("signal", "signal", shifted_mass, roo_mc_m,
                                             roo_mc_signal, ROOT.RooKeysPdf.MirrorBoth, 2)
                # pol2
                roo_n_background = ROOT.RooRealVar('Nbackground', 'N_{bkg}', 10., 1., 2.e6)
                roo_a = ROOT.RooRealVar('a', 'a', 0.11, 0.10, 0.18)
                roo_b = ROOT.RooRealVar('b', 'b', -1.0, -0.01)
                roo_bkg = ROOT.RooPolynomial('background', 'background', roo_m, ROOT.RooArgList(roo_b, roo_a))
                # model
                roo_model = ROOT.RooAddPdf(
                    'model', 'model', ROOT.RooArgList(roo_signal, roo_bkg),
                    ROOT.RooArgList(roo_n_signal, roo_n_background))

                # fit
                ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.ERROR)
                ROOT.RooMsgService.instance().setSilentMode(ROOT.kTRUE)
                ROOT.gErrorIgnoreLevel = ROOT.kError
                r = roo_model.fitTo(roo_data, ROOT.RooFit.Save(), ROOT.RooFit.Extended(ROOT.kTRUE))

                print(f'fit status: {r.status()}')
                if r.status() == 0:

                    # plot
                    nBins = 32
                    xframe = roo_m.frame(2.96, 3.04, nBins)
                    xframe.SetTitle(
                        str(ct_bins[0]) + '#leq #it{c}t<' + str(ct_bins[1]) + ' cm, ' + str(cent_bins[0]) + '-' +
                        str(cent_bins[1]) + '%, ' + str(formatted_eff))
                    xframe.SetName(f'fInvMass_{formatted_eff}')
                    roo_data.plotOn(xframe, ROOT.RooFit.Name('data'))
                    roo_model.plotOn(
                        xframe, ROOT.RooFit.Components('background'),
                        ROOT.RooFit.Name('background'),
                        ROOT.RooFit.LineStyle(ROOT.kDashed),
                        ROOT.RooFit.LineColor(ROOT.kGreen))
                    roo_model.plotOn(xframe, ROOT.RooFit.Components('signal'), ROOT.RooFit.Name('signal'),
                                     ROOT.RooFit.LineStyle(ROOT.kDashed), ROOT.RooFit.LineColor(ROOT.kRed))
                    roo_model.plotOn(xframe, ROOT.RooFit.Name('model'), ROOT.RooFit.LineColor(ROOT.kBlue))

                    formatted_chi2 = "{:.2f}".format(xframe.chiSquare('model', 'data'))
                    roo_model.paramOn(xframe, ROOT.RooFit.Label(
                        '#chi^{2}/NDF = '+formatted_chi2),
                        ROOT.RooFit.Layout(0.68, 0.96, 0.96))

                    print(f'chi2/NDF: {formatted_chi2}, edm: {r.edm()}')
                    if float(formatted_chi2) < 2:
                        # write to file
                        root_file_signal_extraction.cd(f'{bin}')
                        xframe.Write()

                        # fit mc distribution to get sigma and mass
                        roo_mean_mc = ROOT.RooRealVar("mean", "mean", 2.98, 3.0)
                        roo_sigma_mc = ROOT.RooRealVar("sigma", "sigma", 0.001, 0.004)
                        gaus = ROOT.RooGaussian('gaus', 'gaus', roo_m, roo_mean_mc, roo_sigma_mc)
                        gaus.fitTo(roo_mc_signal)

                        # mass
                        mass_val = roo_mean_mc.getVal()-delta_mass.getVal()

                        # significance
                        m_set = ROOT.RooArgSet(roo_m)
                        normSet = ROOT.RooFit.NormSet(m_set)
                        roo_m.setRange(
                            'signalRange', mass_val - 3 * roo_sigma_mc.getVal(),
                            mass_val + 3 * roo_sigma_mc.getVal())
                        signal_int = (
                            roo_model.pdfList().at(0).createIntegral(m_set, normSet, ROOT.RooFit.Range("signalRange"))).getVal()
                        print(f'signal integral = {signal_int}')
                        bkg_int = (
                            roo_model.pdfList().at(1).createIntegral(m_set, normSet, ROOT.RooFit.Range("signalRange"))).getVal()
                        print(f'background integral = {bkg_int}')
                        sig = signal_int*roo_n_signal.getVal()
                        bkg = bkg_int*roo_n_background.getVal()
                        significance_val = sig/np.sqrt(sig+bkg)
                        significance_err = significance_error(sig, bkg)

                        # draw on canvas and save plots
                        canv = ROOT.TCanvas()
                        canv.cd()
                        text_mass = ROOT.TLatex(
                            2.995, 0.9 * xframe.GetMaximum(),
                            "#it{m}_{^{3}_{#Lambda}H} = " + "{:.5f}".format(mass_val) + " GeV/#it{c}")
                        text_mass.SetTextSize(0.035)
                        text_signif = ROOT.TLatex(2.995, 0.82 * xframe.GetMaximum(),
                                                  "S/#sqrt{S+B} = " + "{:.3f}".format(significance_val) + " #pm " +
                                                  "{:.3f}".format(significance_err))
                        text_signif.SetTextSize(0.035)
                        xframe.Draw("")
                        text_mass.Draw("same")
                        text_signif.Draw("same")
                        print(
                            f'significance = {"{:.3f}".format(significance_val)} +/- {"{:.3f}".format(significance_err)}')
                        if not os.path.isdir('plots/signal_extraction'):
                            os.mkdir('plots/signal_extraction')
                        if not os.path.isdir(f'plots/signal_extraction/{bin}'):
                            os.mkdir(f'plots/signal_extraction/{bin}')
                        canv.Print(f'plots/signal_extraction/{bin}/{1-eff_score[0]:.2f}_{bin}.png')

                        # plot kde and mc
                        frame = roo_mc_m.frame(2.96, 3.04, nBins*4)
                        roo_mc_signal.plotOn(frame)
                        roo_signal.plotOn(frame)
                        gaus.plotOn(frame, ROOT.RooFit.LineColor(ROOT.kRed), ROOT.RooFit.LineStyle(ROOT.kDashed))
                        cc = ROOT.TCanvas("cc", "cc")
                        if not os.path.isdir('plots/kde_signal'):
                            os.mkdir('plots/kde_signal')
                        if not os.path.isdir(f'plots/kde_signal/{bin}'):
                            os.mkdir(f'plots/kde_signal/{bin}')
                        frame.Draw()
                        cc.Print(f'plots/kde_signal/{bin}/{formatted_eff}_{bin}.png')

            root_file_signal_extraction.Close()
